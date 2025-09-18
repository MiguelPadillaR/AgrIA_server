import math
import numpy as np
import torch
from dataclasses import dataclass
from rasterio.transform import Affine
import cv2

@dataclass
class BandData:
    path: str
    arr: np.ndarray
    transform: Affine
    crs: any
    width: int
    height: int

def raw_rgb_for_visual(b04, b03, b02):
    """
    Build an RGB image from raw Sentinel-2 bands without percentile stretch.
    Simply rescales 0-max value to 0-255 for uint8 display.
    """
    rgb = np.stack([b04, b03, b02], axis=-1).astype(np.float32)

    # Optional: scale by 0–max of each band
    max_val = np.max(rgb, axis=(0,1), keepdims=True)
    max_val[max_val == 0] = 1  # prevent division by zero
    rgb_u8 = np.clip((rgb / max_val) * 255, 0, 255).astype(np.uint8)
    return rgb_u8


def percentile_stretch(arr: np.ndarray, p_low=2.0, p_high=98.0) -> np.ndarray:
    arr = arr.astype(np.float32)
    if arr.ndim == 3:
        out = np.zeros(arr.shape, dtype=np.uint8)
        for i in range(arr.shape[-1]):
            band = np.nan_to_num(arr[..., i], nan=0.0, posinf=0.0, neginf=0.0)
            vmin, vmax = np.percentile(band, [p_low, p_high])
            vmax = vmax if vmax > vmin else vmin + 1e-3
            out[..., i] = np.clip((band - vmin) / (vmax - vmin) * 255.0, 0, 255).astype(np.uint8)
        return out
    else:
        band = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        vmin, vmax = np.percentile(band, [p_low, p_high])
        vmax = vmax if vmax > vmin else vmin + 1e-3
        return np.clip((band - vmin) / (vmax - vmin) * 255.0, 0, 255).astype(np.uint8)

def stack_bgrn(b02: BandData, b03: BandData, b04: BandData, b08: BandData) -> np.ndarray:
    h, w = b02.arr.shape
    out = np.zeros((h, w, 4), dtype=np.uint16)
    # Correct order: R, G, B, NIR
    out[..., 0], out[..., 1], out[..., 2], out[..., 3] = b04.arr, b03.arr, b02.arr, b08.arr
    return out

def to_torch_4ch(img_bgrn_u16: np.ndarray, device: torch.device) -> torch.Tensor:
    ten = torch.from_numpy(img_bgrn_u16.astype(np.float32)).permute(2,0,1)[None]
    return ten.to(device) / 400


def from_torch_to_u16(sr: torch.Tensor) -> np.ndarray:
    """1x4xHxW -> HxWx4 uint16, reverse of normalization with clipping to prevent artifacts."""
    # Convert to numpy and de-normalize
    sr_denormalized = sr.detach().cpu().numpy() * 400
    
    # Clip the values to the valid range of uint16 to prevent wrap-around artifacts
    np.clip(sr_denormalized, 0, 65535, out=sr_denormalized)
    
    # Safely cast to uint16
    sr_np = sr_denormalized.astype(np.uint16)
    
    # Reshape from 1xCxHxW to HxWxC
    sr_np = np.moveaxis(sr_np[0], 0, -1)
    return sr_np

def make_grid(images, ncols=3, pad=4) -> np.ndarray:
    """Make a grid of images (HxWx3 uint8) with padding."""
    h = max(im.shape[0] for im in images)
    w = max(im.shape[1] for im in images)
    norm = [cv2.copyMakeBorder(im, 0, h - im.shape[0], 0, w - im.shape[1], cv2.BORDER_CONSTANT, value=(255,255,255)) for im in images]
    n = len(norm)
    rows = math.ceil(n / ncols)
    grid = np.ones(((h+pad)*rows+pad, (w+pad)*ncols+pad, 3), dtype=np.uint8) * 255
    for idx, im in enumerate(norm):
        r, c = divmod(idx, ncols)
        y, x = pad + r*(h+pad), pad + c*(w+pad)
        grid[y:y+h, x:x+w] = im
    return grid
