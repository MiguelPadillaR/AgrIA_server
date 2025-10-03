import os
import cv2
import rasterio

import numpy as np

from rasterio.transform import from_origin
from xarray import DataArray
from PIL import Image, ImageEnhance

from ..sr4s.sr.utils import make_grid

from .constants import COMPARISON_PNG_FILEPATH, PNG_DIR, TIF_DIR

# --------------------
# GeoTIFF + PNG export
# --------------------
def reorder_bands(original_s2_numpy, superX):
    # Original: [NIR, B, G, R] -> reorder to [R, G, B, NIR]
    band_order_tif = [3, 2, 1, 0]  # indices in original array
    original_s2_reordered = original_s2_numpy[band_order_tif]
    superX_np = superX.detach().cpu().numpy()
    superX_reordered = superX_np[band_order_tif]
    return original_s2_reordered, superX_reordered

def save_to_tif(array, filepath, sample, sr=False):
    """
    Export a numpy array (bands, H, W) as GeoTIFF.
    
    Args:
        array (np.ndarray): Image data in (bands, H, W).
        filepath (str): Path to save GeoTIFF.
        sample (xarray.DataArray or rioxarray obj): Source for bounds + resolution.
        sr (bool): If True, adjust transform for super-res image.
    """
    # Spatial bounds and resolution from sample
    minx, __, __, maxy = sample.rio.bounds()
    res_x, res_y = sample.rio.resolution()
    
    if sr:
        # Scale factor = ratio of super-res width to sample width
        scale = array.shape[1] / sample.shape[1]
        new_res_x = abs(res_x) / scale
        new_res_y = abs(res_y) / scale
        transform = from_origin(minx, maxy, new_res_x, new_res_y)
    else:
        transform = from_origin(minx, maxy, abs(res_x), abs(res_y))
    
    save_as_tif(array, filepath, transform)

def save_as_tif(image_nparray,filepath, transform, crs:str="EPSG:32630"):
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
        transform=transform
    ) as dst:
        dst.write(image_nparray)

    print(f"✅ Saved {filepath} with corrected band order")

def save_to_png(image_nparray, filepath):
    # Create PNG output dir
    os.makedirs(PNG_DIR, exist_ok=True)
    image_nparray = brighten(image_nparray)
    save_png(image_nparray, filepath)
    print(f"✅ Saved {filepath} with correct colors")

def brighten(img, factor=2.5):
    """Brighten both by scaling and clipping"""
    return np.clip(img * factor, 0, 1)

def save_png(arr, path, enhance_contrast=False, contrast_factor=1.5, apply_gamma=False, gamma=1.6, transparent_nodata=True):
    """
    Save an RGB raster (bands, H, W) as PNG with optional contrast, gamma correction,
    and transparent background for nodata areas.

    - `enhance_contrast`: apply linear contrast boost
    - `contrast_factor`: multiplier for contrast enhancement (>1 = more contrast)
    - `apply_gamma`: apply gamma correction for punchy blacks/whites
    - `gamma` <1 darkens shadows / brightens highlights
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
    if apply_gamma:
        rgb_norm = np.clip(rgb_norm ** gamma, 0, 1)

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

def get_cloudless_time_indices(scl: DataArray, cloud_threshold = 0.01):

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
            
    if len(valid_indices) == 0 and min_index > -1:
        print(f"No time indices with cloud fraction <= {cloud_threshold:.3%}. Using index {min_index} with minimum cloud fraction {min_threshold:.3%}.")
        valid_indices.append(min_index)
    print("Valid time indices (cloud < 1%):", valid_indices)
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


def make_comparison_grid(original, superres):
    """
    Creates side-by-side comparison grid of original vs SR image.
    original, superres: arrays (bands,H,W) with [NIR,B,G,R] order.
    """
    og_img = prepare_rgb(original)          # convert to RGB
    sr_img = prepare_rgb(superres, True)    # tensor → numpy → RGB

    # Resize original to match SR dimensions
    h_ref, w_ref = sr_img.shape[:2]
    og_img_resized = cv2.resize(og_img, (w_ref, h_ref), interpolation=cv2.INTER_CUBIC)

    # Make grid
    grid = make_grid([og_img_resized, sr_img], ncols=2)
    Image.fromarray(grid).save(COMPARISON_PNG_FILEPATH)
    print(f"✅ Saved comparison grid: {COMPARISON_PNG_FILEPATH}")
