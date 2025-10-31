import math
import os
import cv2
import rasterio

import numpy as np

from rasterio.transform import from_bounds
from xarray import DataArray
from PIL import Image, ImageEnhance

from ...config.constants import GET_SR_BENCHMARK

from ...benchmark.sr.utils import copy_file_to_dir
from .constants import BRIGHTNESS_FACTOR, COMPARISON_PNG_FILEPATH, GAMMA, PNG_DIR, SPAIN_MAINLAND, TIF_DIR

# --------------------
# GeoTIFF + PNG export
# --------------------
def reorder_bands(original_s2_numpy, superX):
    """
    Reorders image bands from NIR,B,G,R to R,G,B,NIR
    """
    # Original: [NIR, B, G, R] -> reorder to [R, G, B, NIR]
    band_order_tif = [3, 2, 1, 0]  # indices in original array
    original_s2_reordered = original_s2_numpy[band_order_tif]
    superX_np = superX.detach().cpu().numpy()
    superX_reordered = superX_np[band_order_tif]
    return original_s2_reordered, superX_reordered

def save_to_tif(array, filepath, sample, crs: str):
    """
    Export a numpy array (bands, H, W) as GeoTIFF.
    
    Arguments:
        array (np.ndarray): Image data in (bands, H, W).
        filepath (str): Path to save GeoTIFF.
        sample (xarray.DataArray or rioxarray obj): Source for bounds + resolution.
        sr (bool): If True, adjust transform for super-res image.
    """
    # Spatial bounds and resolution from sample
    minx, miny, maxx, maxy = sample.rio.bounds()
    height, width = array.shape[1], array.shape[2]
    transform = from_bounds(minx, miny, maxx, maxy, width, height)

    save_tif(array, filepath, transform, crs)

def save_tif(image_nparray, filepath, adjust_transform, crs:str="EPSG:32630"):
    """
    Uses `rasterio` to save a GeoTIFF image
    """
    # Create output TIF dir
    os.makedirs(TIF_DIR, exist_ok=True)
    # Save as TIF
    with rasterio.open(
        filepath, "w",
        driver="GTiff",
        height=image_nparray.shape[1],
        width=image_nparray.shape[2],
        count=image_nparray.shape[0],
        dtype="float32",
        crs=crs,
        transform=adjust_transform
    ) as dst:
        dst.write(image_nparray)

    if GET_SR_BENCHMARK:
        print("Copying SEN2SR TIF file...")
        if "original" in str(filepath):
            print("Copying original file for benchmark...")
            copy_file_to_dir(filepath, is_sr4s=None)
        else:
            print("Copying SEN2SR file for benchmark...")
            copy_file_to_dir(filepath)

    print(f"✅ Saved {filepath} with corrected band order")

def save_to_png(image_nparray, filepath, lat=None, apply_gamma_correction=False):
    """
    Wrapper for saving a NumPy RGB array as PNG, optionally applying
    latitude-based brightness normalization.
    
    Args:
        image_nparray (np.ndarray): Input image (bands, H, W)
        filepath (str): Output PNG path
        lat (float, optional): Latitude for brightness normalization
        apply_gamma_correction (bool): Whether to apply gamma correction
    """
    os.makedirs(PNG_DIR, exist_ok=True)

    # Apply latitude-based brightness normalization if latitude provided
    if lat is not None:
        brightness_factor = np.clip(1.0 / np.cos(np.deg2rad(lat)), 0.7, 1.3)
        image_nparray = np.clip(image_nparray * brightness_factor, 0, 1)
        print(f"🧭 Applied latitude-based brightness correction (lat={lat:.2f}, factor={brightness_factor:.3f})")

    # Continue with normal save pipeline
    save_png(image_nparray, filepath, apply_gamma_correction=apply_gamma_correction)
    print(f"✅ Saved {filepath} with corrected colors and brightness normalization")

def save_png(arr, path, enhance_contrast=True, contrast_factor=1.5, apply_gamma_correction=False, gamma=GAMMA, transparent_nodata=True):
    """
    Save an RGB raster (bands, H, W) as PNG with optional contrast, gamma correction,
    and transparent background for nodata areas.

    - `enhance_contrast`: apply linear contrast boost
    - `contrast_factor`: multiplier for contrast enhancement (>1 = more contrast)
    - `apply_gamma`: apply gamma correction for punchy blacks/whites
    - `gamma` darkens shadows / brightens highlights
    - `transparent_nodata`: if True, black nodata areas will be transparent
    """
    rgb = np.transpose(arr[:3], (1, 2, 0))  # (H,W,3)

    # Normalize to 0-1 safely
    rgb_min, rgb_max = rgb.min(), rgb.max()
    if rgb_max > rgb_min:
        rgb_norm = (rgb - rgb_min) / (rgb_max - rgb_min)
    else:
        rgb_norm = np.zeros_like(rgb, dtype=float)

    # Apply gamma correction if requested
    if apply_gamma_correction:
        rgb_norm = apply_gamma(rgb_norm, gamma)
    
    # Scale to 0-255
    rgb_uint8 = (rgb_norm * 255).astype(np.uint8)

    # Start with RGBA image
    img = Image.fromarray(rgb_uint8, mode="RGB").convert("RGBA")
    data = np.array(img)

    # Make nodata (all 0s) transparent
    if transparent_nodata:
        mask = np.all(rgb_uint8 == 0, axis=-1)  # nodata = all channels == 0
        data[mask, 3] = 0  # alpha = 0

    # Apply contrast enhancement if requested
    img = Image.fromarray(data, mode="RGBA")
    if enhance_contrast:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(contrast_factor)

    img.save(path, "PNG")

def brighten(img, factor=BRIGHTNESS_FACTOR):
    """Brighten both by scaling and clipping"""
    return np.clip(img * factor, 0, 1)

def apply_gamma(img, gamma = GAMMA):
    return np.clip(img ** (1 / gamma), 0, 1)

def get_cloudless_time_indices(scl: DataArray, cloud_threshold = 0.01):
    """
    Uses the SCL band and combs over the image data within date range to find the least cloudy.
    Arguments:
        scl (DataArray): SCL band info
        cloud_threshold (float): Tolerated cloud density percentage. Default: 0.01 (0.00-1.00)
    Returns:
        valid_indices (list): List of all valid dates' indices within acceptable cloud threshold
    """
    valid_indices = []
    min_threshold = 1  # 100%
    min_index = -1
    for t in range(scl.shape[0]):  # iterate over time dimension
        scl_slice = scl.isel(time=t).compute().to_numpy()
        # Get cloud image coverage
        total_pixels = scl_slice.size
        cloud_pixels = np.isin(scl_slice, [7, 8, 9, 10]).sum()
        cloud_fraction = cloud_pixels / total_pixels
        
        print(f"Time {t}: cloud_fraction={cloud_fraction:.3%}")
        
        if cloud_fraction <= cloud_threshold:
            valid_indices.append(t)
        elif cloud_fraction < min_threshold:
            min_threshold = cloud_fraction
            min_index = t
    
    if len(valid_indices) == 0:
        if min_index > -1:
            print(f"No time indices with cloud fraction <= {cloud_threshold:.3%}. Using index {min_index} with minimum cloud fraction {min_threshold:.3%}.")
            valid_indices.append(min_index)
        else:
           # No valid or even partially valid images found
            raise ValueError(
                f"❌ No cloud-free or minimally cloudy Sentinel-2 images found (min threshold = {min_threshold:.2%}) "
                f"for the selected area and date range (original threshold = {cloud_threshold:.2%})."
            ) 
    print(f"Valid time indices (cloud = {min_threshold:.2%}):", valid_indices)
    return valid_indices

def prepare_rgb(arr, is_tensor=False):
    """
    Convert (bands, H, W) array to RGB uint8 (H, W, 3).
    Assumes arr has bands in order [NIR, B, G, R] -> we take R,G,B.
    """
    if is_tensor:
        arr = arr.detach().cpu().numpy()
    
    # Take only R,G,B
    rgb = np.stack([arr[3], arr[2], arr[1]], axis=-1)  # (H,W,3)
    
    # Normalize to 0–255
    rgb_norm = (rgb - rgb.min()) / (rgb.max() - rgb.min() + 1e-6)
    return (rgb_norm * 255).astype(np.uint8)

def make_pixel_faithful_comparison(original_arr, sr_arr, output_path=COMPARISON_PNG_FILEPATH, apply_brightness=True, apply_gamma=False, border=15, spacing=5, bg_color=(255, 255, 255)):
    """
    Create a side-by-side comparison between original and SR images with
    white borders and padding. The original is upscaled with nearest-neighbor
    to match SR size (preserves pixelation).
    """

    if not isinstance(sr_arr, np.ndarray):
        sr_arr = sr_arr.detach().cpu().numpy()

    def normalize_and_brighten(arr):
        arr = arr[:3]
        rgb = np.transpose(arr, (1, 2, 0))
        rgb_min, rgb_max = rgb.min(), rgb.max()
        if rgb_max > rgb_min:
            rgb = (rgb - rgb_min) / (rgb_max - rgb_min)
        rgb = brighten(rgb) if apply_brightness else rgb
        rgb = apply_gamma(rgb) if apply_gamma else rgb
        return (rgb * 255).astype(np.uint8)

    img_original = normalize_and_brighten(original_arr)
    img_sr = normalize_and_brighten(sr_arr)

    # Match sizes
    target_size = (img_sr.shape[1], img_sr.shape[0])
    img_original_upscaled = np.array(
        Image.fromarray(img_original).resize(target_size, resample=Image.NEAREST)
    )

    # Convert to PIL and add white border
    def add_border(img_np):
        img = Image.fromarray(img_np)
        bordered = Image.new("RGB", (img.width + 2 * border, img.height + 2 * border), bg_color)
        bordered.paste(img, (border, border))
        return bordered

    img_original_bordered = add_border(img_original_upscaled)
    img_sr_bordered = add_border(img_sr)

    # Canvas size
    total_width = img_original_bordered.width + img_sr_bordered.width + spacing
    total_height = max(img_original_bordered.height, img_sr_bordered.height)

    canvas = Image.new("RGB", (total_width, total_height), bg_color)
    canvas.paste(img_original_bordered, (0, (total_height - img_original_bordered.height) // 2))
    canvas.paste(img_sr_bordered, (img_original_bordered.width + spacing,
                                   (total_height - img_sr_bordered.height) // 2))

    # Add labels
    # draw = ImageDraw.Draw(canvas)
    # font = ImageFont.load_default()
    # draw.text((border, 10), "Original Sentinel (nearest-neighbor upscaled)", fill=(0, 0, 0), font=font)
    # draw.text((img_original_bordered.width + spacing + border, 10),
    #           "Super-Resolved (native resolution)", fill=(0, 0, 0), font=font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path)
    print(f"✅ Saved pixel-faithful comparison with padding → {output_path}")

def lonlat_to_utm_epsg(lon, lat):
    """
    Get correct CRS from coordinates
    """
    zone = int(math.floor((lon + 180) / 6) + 1)
    if lat >= 0:
        return f"EPSG:{32600 + zone}"  # Northern hemisphere
    else:
        return f"EPSG:{32700 + zone}"  # Southern hemisphere
# Load Spain shapefile (or GeoJSON)

def is_in_spain(lon, lat):
    """Return True if a lon/lat point is inside mainland Spain bbox."""
    min_lon, min_lat, max_lon, max_lat = SPAIN_MAINLAND
    return (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)
