import numpy as np
from PIL import Image, ImageEnhance
from xarray import DataArray

# --------------------
# PNG export
# --------------------

def save_png(arr, path, enhance_contrast=False, contrast_factor=1.2, apply_gamma=False, gamma=1.6, transparent_nodata=True):
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


def brighten(img, factor=2.5):
    """Brighten both by scaling and clipping"""
    return np.clip(img * factor, 0, 1)

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
