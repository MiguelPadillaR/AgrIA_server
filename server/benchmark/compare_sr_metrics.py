import rasterio
import numpy as np
import pandas as pd
from skimage.metrics import structural_similarity as ssim, peak_signal_noise_ratio as psnr
from datetime import datetime
import cv2, os, glob

from .constants import BM_DIR, BM_DATA_DIR, BM_RES_DIR, BM_SR_DIR


EPS = 1e-10

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

def compute_metrics_for_folder(gt_path, sr_folder, output_dir="results", ratio=2, auto_normalize=True):
    # Load GT
    with rasterio.open(gt_path) as gt_src:
        gt = gt_src.read().astype(np.float32)
    gt = np.moveaxis(gt, 0, -1)  # CHW -> HWC
    gt_shape = gt.shape[:2]
    gt_bands = gt.shape[-1]

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_path = os.path.join(output_dir, f"benchmark_results_{timestamp}.csv")

    rows = []

    sr_files = sorted(glob.glob(os.path.join(sr_folder, "*.tif")))
    if len(sr_files) == 0:
        raise FileNotFoundError(f"No TIFF files found in {sr_folder}")

    for sr_path in sr_files:
        row = {
            "timestamp_run": timestamp,
            "filename_gt": os.path.basename(gt_path),
            "filename_sr": os.path.basename(sr_path),
            "Resized": False,
            "Bands_match": False,
            "Normalized": False,
            "Normalization_method": None,
            "Warnings": ""
        }
        try:
            with rasterio.open(sr_path) as sr_src:
                sr = sr_src.read().astype(np.float32)
            sr = np.moveaxis(sr, 0, -1)

            row["sr_orig_min"] = float(np.nanmin(sr))
            row["sr_orig_max"] = float(np.nanmax(sr))
            row["gt_orig_min"] = float(np.nanmin(gt))
            row["gt_orig_max"] = float(np.nanmax(gt))

            # band check
            if sr.shape[-1] != gt_bands:
                row["Warnings"] = f"band_mismatch ({sr.shape[-1]} vs {gt_bands})"
                print("⚠️", row["Warnings"], "Skipping:", sr_path)
                rows.append(row)
                continue
            row["Bands_match"] = True

            # Resize if needed
            if sr.shape[:2] != gt_shape:
                sr = resize_image(sr, gt_shape)
                row["Resized"] = True

            # Detect and normalize if necessary
            sr_mapped, normalized, method, per_band_stats, warnings = detect_and_normalize(sr, gt, auto_normalize=auto_normalize)
            row["Normalized"] = normalized
            row["Normalization_method"] = method
            if warnings:
                row["Warnings"] = "; ".join(warnings)

            # Compute metrics (use GT range for data_range where needed)
            data_range = float(np.nanmax(gt) - np.nanmin(gt) + EPS)
            try:
                row["PSNR"] = float(psnr(gt, sr_mapped, data_range=data_range))
            except Exception as e:
                row["PSNR"] = np.nan
                row["Warnings"] += f"; psnr_error:{e}"

            try:
                row["SSIM"] = float(ssim(gt, sr_mapped, channel_axis=2, data_range=data_range))
            except Exception as e:
                # fallback older skimage signature (multi_channel)
                try:
                    row["SSIM"] = float(ssim(gt, sr_mapped, multichannel=True, data_range=data_range))
                except Exception as e2:
                    row["SSIM"] = np.nan
                    row["Warnings"] += f"; ssim_error:{e2}"

            row["RMSE"] = float(np.sqrt(np.mean((gt - sr_mapped)**2)))
            row["SAM_rad"] = float(spectral_angle_mapper(gt, sr_mapped))
            row["ERGAS"] = float(ergas(sr_mapped, gt, ratio=ratio))

            # attach per-band stats summary (optionally save more detailed JSON elsewhere)
            for b, band_stats in enumerate(per_band_stats):
                row[f"band{b}_gt_min"] = band_stats["gt_min"]
                row[f"band{b}_gt_max"] = band_stats["gt_max"]
                row[f"band{b}_sr_min"] = band_stats["sr_min"]
                row[f"band{b}_sr_max"] = band_stats["sr_max"]

            print(f"✅ Processed {os.path.basename(sr_path)} | PSNR={row.get('PSNR'):.3f} SSIM={row.get('SSIM'):.4f}")
        except Exception as e:
            row["Warnings"] = f"error_processing:{e}"
            print("❌ Error processing", sr_path, e)
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    print(f"\n📁 All results saved to: {csv_path}")
    print(df)
    print(df[["filename_gt","filename_sr","Resized","PSNR","SSIM","RMSE","SAM_rad","ERGAS"]])
    return csv_path

def check_normalization(filelist):
    print("Files:", filelist)
    for path in filelist:
        with rasterio.open(path) as src:
            arr = src.read(1).astype(np.float32)
        print(path, np.min(arr), np.max(arr))

# Example usage:
GT_FILE = BM_DATA_DIR / "original.tif"

os.makedirs(BM_SR_DIR, exist_ok=True)
os.makedirs(BM_RES_DIR, exist_ok=True)

compute_metrics_for_folder(GT_FILE, BM_SR_DIR, output_dir=BM_RES_DIR, ratio=2, auto_normalize=True)

# Get all files list:
filelist = [BM_SR_DIR / file for file in os.listdir(BM_SR_DIR)]
filelist.append(GT_FILE)

# check_normalization(filelist)
