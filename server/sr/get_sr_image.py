import os
import glob
from pathlib import Path
import cv2
import numpy as np
import time
import torch
import rasterio

from PIL import Image

from ..config.constants import SR_BANDS

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

def process_directory(input_dir, output_dir=CURR_SCRIPT_DIR / 'sr_5m'):
    """
    Process directory where image bands are found for all images found and super-resolves them.
    Saves SR image and comparison image between original and SR version.
    Generates output dir if it doesn't exist
    Arguments:
        input_dir (str | Path): Input directory path
        output_dir (str | Path): Output directory path. Default is `sr/sr_5m`
    """
    start_time = time.time()

    all_files = glob.glob(os.path.join(input_dir, "*.tif*"))
    groups = {}

    # Group filenames with respective band file paths
    for f in all_files:
        base = os.path.basename(f)
        band = next((el for el in SR_BANDS if el in base), None)
        if band is None:
            continue
        filename, __ = os.path.splitext(base)
        prefix = filename.rsplit(band, 1)[0]
        if prefix not in groups:
            groups[prefix] = {}
        groups[prefix][band] = f

    # Perform SR if filename has all SR_BANDS files
    for prefix, band_files in groups.items():
        missing = set(SR_BANDS) - set(band_files.keys())
        if missing:
            print(f"Skipping {prefix}, missing bands: {missing}")
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
        out_png = os.path.join(output_dir, 'out', f"{prefix}.png")
        save_rgb_png(sr_u16, out_png)
        print(f"Saved PNG: {out_png}")

        # Make and save comparison grid
        comp_dir = output_dir / "comparison"
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_png = comp_dir / f"{prefix}_comparison.png"
        grid = make_grid([rgb_before_u8_resized,
                        percentile_stretch(np.stack([sr_u16[...,2], sr_u16[...,1], sr_u16[...,0]], axis=-1))],
                        ncols=2
        )
        Image.fromarray(grid).save(comp_png)
        print(f"Saved comparison grid: {comp_png}")

        print(f"\nTotal time taken:\t{(time.time() - start_time)/60:.1f} minutes")