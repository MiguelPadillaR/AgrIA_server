from datetime import datetime
import os
import glob
from pathlib import Path
import cv2
import numpy as np
import time
import torch
import rasterio

from PIL import Image

from ....benchmark.sr.constants import BM_DATA_DIR

from ....config.constants import GET_SR_BENCHMARK, SR_BANDS, SR5M_DIR
from ....benchmark.sr.utils import copy_file_to_dir

from .utils import percentile_stretch, stack_bgrn, make_grid
from .L1BSR_wrapper import L1BSR

CURR_SCRIPT_DIR = Path(__file__).resolve().parent

# --- Device ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# --- Load model ---
ENGINE = L1BSR(weights_path=CURR_SCRIPT_DIR / "REC_Real_L1B.safetensors", device=DEVICE)

def save_rgb_png(sr, out_path):
    """Save SR result as stretched RGB PNG"""
    rgb = np.stack([sr[..., 2], sr[..., 1], sr[..., 0]], axis=-1)  # B04,R / B03,G / B02,B
    rgb_u8 = percentile_stretch(rgb)
    Image.fromarray(rgb_u8).save(out_path)

def save_multiband_tif(sr: np.ndarray, reference_band: str, out_path: str):
    """
    Save SR result as multiband GeoTIFF using metadata from a reference band.
    Assumes sr has shape (H, W, 4).
    """
    with rasterio.open(reference_band) as src:
        profile = src.profile

    h, w, c = sr.shape
    transform = profile["transform"]

    # Scale transform if SR resolution changed
    if h != profile["height"] or w != profile["width"]:
        scale_x = profile["width"] / w
        scale_y = profile["height"] / h
        transform = rasterio.Affine(
            profile["transform"].a * scale_x,
            profile["transform"].b,
            profile["transform"].c,
            profile["transform"].d,
            profile["transform"].e * scale_y,
            profile["transform"].f,
        )

    # Replace NaN or inf with 0
    sr_clean = np.nan_to_num(sr, nan=0, posinf=0, neginf=0).astype(np.uint16)

    profile.update({
        "height": h,
        "width": w,
        "transform": transform,
        "count": c,
        "dtype": rasterio.uint16,
        "compress": "lzw",
        "nodata": 0,   # mark 0 as nodata
    })

    with rasterio.open(out_path, "w", **profile) as dst:
        for i in range(c):
            dst.write(sr_clean[..., i], i + 1)
            dst.set_band_description(i + 1, f"B{i+1}")  # optional: label bands

def process_directory(input_dir, output_dir=SR5M_DIR, save_as_tif=True):
    """
    Process directory where image bands are found for all images found and super-resolves them.
    Saves SR image and comparison image between original and SR version.
    Generates output dir if it doesn't exist
    Arguments:
        input_dir (str | Path): Input directory path
        output_dir (str | Path): Output directory path. Default is `sr/sr_5m`
        save_as_tif (bool): If `True`, saves uncropped SR image as TIF. Default to `True`.
    Returns:
        (str): SR PNG filename (even if also saved as TIF).
    """
    start_time = datetime.now()

    all_files = glob.glob(os.path.join(input_dir, "*.tif*"))
    groups = {}

    sr_image_path = None

    # Group filenames with respective band file paths
    for f in all_files:
        base = os.path.basename(f)
        band = next((el for el in SR_BANDS if el in base), None)
        if band is None:
            continue
        filename, __ = os.path.splitext(base)
        prefix_parts = filename.split(f"-{band}", 1)[0].split('_')
        sr_prefix = f'SR_{prefix_parts[0]}_{prefix_parts[1]}'
        og_prefix = f'GT_SR4S'
        if sr_prefix not in groups:
            groups[sr_prefix] = {}
        groups[sr_prefix][band] = f

    # Perform SR if filename has all SR_BANDS files
    for sr_prefix, band_files in groups.items():
        missing = set(SR_BANDS) - set(band_files.keys())
        if missing:
            print(f"Skipping {sr_prefix}, missing bands: {missing}")
            continue

        b02 = rasterio.open(band_files["B02"]).read(1)
        b03 = rasterio.open(band_files["B03"]).read(1)
        b04 = rasterio.open(band_files["B04"]).read(1)
        b08 = rasterio.open(band_files["B08"]).read(1)

        # Get original RGB image
        rgb_before_u16 = np.stack([b04, b03, b02], axis=-1)
        rgb_before_u8 = percentile_stretch(rgb_before_u16)
        h, w, _ = rgb_before_u8.shape

        rgb_before_u8_resized = np.array(Image.fromarray(rgb_before_u8).resize((w*2, h*2), cv2.INTER_NEAREST))

        # Stack input
        img_bgrn = stack_bgrn(
            type("Band", (), {"arr": b02}),
            type("Band", (), {"arr": b03}),
            type("Band", (), {"arr": b04}),
            type("Band", (), {"arr": b08}),
        )

        # Run SR
        sr_u16 = ENGINE.super_resolve(img_bgrn)

        # Save PNG
        output_dir.mkdir(parents=True, exist_ok=True)
        out_png = os.path.join(output_dir, f"{sr_prefix}.png")
        sr_image_path = out_png
        save_rgb_png(sr_u16, out_png)
        print(f"Saved PNG: {out_png}")

        # Save TIF
        if save_as_tif or GET_SR_BENCHMARK:
            sr_out_tif = os.path.join(output_dir, f"{sr_prefix}.tif")
            timestamp = str(time.time())
            og_out_tif = os.path.join(BM_DATA_DIR, f"{timestamp}_{og_prefix}.tif")
            save_multiband_tif(sr_u16, band_files["B02"], sr_out_tif)
            print(f"Saved TIF: {sr_out_tif}")
            save_multiband_tif(img_bgrn, band_files["B02"], og_out_tif)
            print(f"Saved TIF: {og_out_tif}")
            if GET_SR_BENCHMARK:
                copy_file_to_dir(sr_out_tif, is_sr4s=True)

        # Make and save comparison grid
        comp_dir = output_dir / "comparison"
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_png = comp_dir / f"{sr_prefix}_comparison.png"
        grid = make_grid([rgb_before_u8_resized,
                        percentile_stretch(np.stack([sr_u16[...,2], sr_u16[...,1], sr_u16[...,0]], axis=-1))],
                        ncols=2
        )
        Image.fromarray(grid).save(comp_png)
        print(f"Saved comparison grid: {comp_png}")

        print(f"\nTotal time taken:\t{datetime.now() - start_time}")
    return sr_image_path
