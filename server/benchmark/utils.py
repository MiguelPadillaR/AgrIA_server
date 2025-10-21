import cv2
import os, re
import numpy as np
import shutil
import time

from .constants import BM_SR_DIR, BM_DATA_DIR

EPS = 1e-10

def copy_file_to_dir(src, dest_dir = BM_SR_DIR, is_sr4s: bool = False):
    """
    Copy source file to destiny dir. Used mainly to copy SR TIFs into `BM_SR_DIR`
    Arguments:
        src (str): Source file to copy from.
        dest_dir (str): Dir to copy file to. De.fault is `BM_SR_DIR`.
    Returns:
        dest_path (str): Full destiny filepath.
    """
    # Extract the filename and extension
    __, ext = os.path.splitext(src)
    if type(is_sr4s) is not bool:
        dest_dir = BM_DATA_DIR
        name = f"GT_SEN2SR"
    else:
        name = "SR4S" if is_sr4s else "SEN2SR"
    timestamp = str(time.time())
    filename =  f"{timestamp}_{name}{ext}"

    # Construct the initial destination path
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    # Check for conflicts and rename if necessary
    #    counter = 1
    #    while os.path.exists(dest_path):
    #        dest_path = os.path.join(dest_dir, f"{filename}_{counter}{ext}")
    #        counter += 1
    # Copy the file to the resolved destination path
    shutil.copy2(src, dest_path)
    print(f"\nFile copied for benchmark to: {dest_path}\n")
    return dest_path

def extract_timestamp(filename: str):
    """Extract leading numeric timestamp from filename (before underscore)."""
    match = re.match(r"(\d+\.\d+)_", filename)
    return float(match.group(1)) if match else None

def find_closest_sr(timestamp, sr_files, model_tag, tolerance=10.0):
    """
    Find SR file of a given model with timestamp closest to target within tolerance.
    Returns full path or None if not found.
    """
    best_file, min_diff = None, float("inf")
    for f in sr_files:
        if model_tag not in f:
            continue
        ts = extract_timestamp(os.path.basename(f))
        if ts is None:
            continue
        diff = abs(ts - timestamp)
        if diff < min_diff and diff <= tolerance:
            best_file, min_diff = f, diff
    return best_file

def spectral_angle_mapper(img1, img2):
    """Mean SAM across pixels (img shape H,W,B). Returns radians."""
    # Flatten pixels x bands
    a = img1.reshape(-1, img1.shape[-1])
    b = img2.reshape(-1, img2.shape[-1])
    dot = np.sum(a * b, axis=1)
    denom = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + EPS
    angles = np.arccos(np.clip(dot / denom, -1.0, 1.0))
    return np.mean(angles)

def ergas(sr, gt, ratio=2):
    """ERGAS metric. ratio = resolution_LR / resolution_HR (e.g., 2 for 20->10m)."""
    gt = gt.astype(np.float64)
    sr = sr.astype(np.float64)
    mean_gt = np.mean(gt, axis=(0,1))
    mse = np.mean((sr - gt)**2, axis=(0,1))
    # Avoid divide by zero for mean_gt
    denom = (mean_gt**2 + EPS)
    return 100.0 * ratio * np.sqrt(np.mean(mse / denom))

def resize_image(img, target_shape):
    """
    Resize HxWxB image to target_shape (h, w) using bicubic interpolation.
    img: numpy array HxWxB
    """
    Ht, Wt = target_shape
    bands = img.shape[-1]
    out = np.zeros((Ht, Wt, bands), dtype=np.float32)
    for b in range(bands):
        out[..., b] = cv2.resize(img[..., b], (Wt, Ht), interpolation=cv2.INTER_CUBIC)
    return out

def detect_and_normalize(sr, gt, auto_normalize=True):
    """
    Decide whether to normalize sr to gt. Returns (sr_mapped, normalized_flag, method, per_band_stats, warnings)
    Normalization logic:
      - Compute per-band max ratios sr_max / (gt_max + EPS). If median ratio > 5 or < 0.2 => we map per-band SR range -> GT range.
      - Otherwise do nothing (assume same units).
    The mapping is per-band linear mapping:
      sr_mapped_b = (sr_b - sr_b_min)/(sr_b_max - sr_b_min) * (gt_b_max - gt_b_min) + gt_b_min
    """
    warnings = []
    sr = sr.astype(np.float32)
    gt = gt.astype(np.float32)

    bands = gt.shape[-1]
    per_band_stats = []
    ratios = []
    for b in range(bands):
        gt_b = gt[..., b]
        sr_b = sr[..., b]
        gt_min, gt_max = float(np.nanmin(gt_b)), float(np.nanmax(gt_b))
        sr_min, sr_max = float(np.nanmin(sr_b)), float(np.nanmax(sr_b))
        per_band_stats.append({
            "band": b,
            "gt_min": gt_min, "gt_max": gt_max,
            "sr_min": sr_min, "sr_max": sr_max
        })
        # compute ratio safely
        ratios.append((sr_max / (gt_max + EPS)) if (gt_max + EPS) != 0 else np.inf)

    median_ratio = float(np.median(ratios))
    # Heuristics to decide mapping
    normalized = False
    method = "none"

    if auto_normalize:
        # If GT looks like [0..1] and SR is on a much larger numeric scale OR the median ratio is huge/small -> map
        if median_ratio > 5.0 or median_ratio < 0.2 or np.nanmax([s["sr_max"] for s in per_band_stats]) > 1000 and np.nanmax([s["gt_max"] for s in per_band_stats]) <= 1.5:
            # map per-band
            sr_mapped = np.empty_like(sr, dtype=np.float32)
            for b in range(bands):
                smin = per_band_stats[b]["sr_min"]
                smax = per_band_stats[b]["sr_max"]
                gmin = per_band_stats[b]["gt_min"]
                gmax = per_band_stats[b]["gt_max"]
                if (smax - smin) < EPS:
                    # constant band in SR: set to GT mean (avoid divide by zero)
                    sr_mapped[..., b] = np.full(sr[..., b].shape, np.nanmean(gt[..., b]), dtype=np.float32)
                    warnings.append(f"band_{b}_constant_sr; set to gt_mean")
                else:
                    sr_norm = (sr[..., b] - smin) / (smax - smin)
                    sr_mapped[..., b] = (sr_norm * (gmax - gmin)) + gmin
            normalized = True
            method = "per_band_mapped_to_gt_range"
        else:
            sr_mapped = sr  # do nothing
            normalized = False
            method = "none"
    else:
        sr_mapped = sr
        normalized = False
        method = "auto_normalize_disabled"

    return sr_mapped, normalized, method, per_band_stats, warnings


