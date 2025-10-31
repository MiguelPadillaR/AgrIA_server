import rasterio
import numpy as np
import pandas as pd
from skimage.metrics import structural_similarity as ssim, peak_signal_noise_ratio as psnr
from datetime import datetime
import os, glob

from .constants import BM_DATA_DIR, BM_SR_DIR, BM_RES_DIR
from .utils import *

def compare_sr_metrics(gt_dir: str=BM_DATA_DIR, sr_dir: str=BM_SR_DIR):
    gt_files = sorted(glob.glob(str(gt_dir / "*.tif")))
    sr_files = sorted(glob.glob(str(sr_dir / "*.tif")))

    if not gt_files or not sr_files:
        raise FileNotFoundError("Missing ground truth or SR files")

    print(f"Found {len(gt_files)} ground truths and {len(sr_files)} SR images.")

    paired = {}

    # Pair GT with corresponding SR images
    for gt_path in gt_files:
        gt_name = os.path.basename(gt_path)
        ts_gt = extract_timestamp(gt_name)
        if ts_gt is None:
            print(f"⚠️ Skipping {gt_name} (no timestamp found)")
            continue

        sr_sen2sr = find_closest_sr(ts_gt, sr_files, "SEN2SR")
        sr_sr4s = find_closest_sr(ts_gt, sr_files, "SR4S")

        paired[ts_gt] = {
            "gt": gt_path,
            "SEN2SR": sr_sen2sr,
            "SR4S": sr_sr4s
        }

    all_rows = []

    # Run once per GT + model
    for ts, files in paired.items():
        gt_path = files["gt"]
        for model_name in ["SEN2SR", "SR4S"]:
            sr_path = files[model_name]
            if not sr_path or not os.path.exists(sr_path):
                print(f"⚠️ Missing {model_name} for timestamp {ts}")
                continue

            print(f"\n🚀 Benchmarking {model_name} for {os.path.basename(gt_path)} ...")
            row = compute_metrics_for_pair(
                gt_path,
                sr_path,
                model_name=model_name,
                ratio=2,
                auto_normalize=True
            )
            if row:
                all_rows.append(row)

    # Write one combined CSV
    os.makedirs(BM_RES_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_path = os.path.join(BM_RES_DIR, f"benchmark_results_combined_{timestamp}.csv")

    df = pd.DataFrame(all_rows)
    df.to_csv(csv_path, index=False)
    print(f"\n✅ Combined benchmark complete for all pairs.")
    print(f"📁 Saved combined results to: {csv_path}")
    print(df[["filename_gt", "filename_sr", "model_name", "PSNR", "SSIM", "RMSE", "SAM_rad", "ERGAS"]])
    return csv_path

def compute_metrics_for_pair(gt_path, sr_path, model_name=None, ratio=2, auto_normalize=True):
    """Compute metrics for a single GT/SR pair."""
    row = {
        "timestamp_run": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
        "model_name": model_name,
        "filename_gt": os.path.basename(gt_path),
        "filename_sr": os.path.basename(sr_path),
        "Resized": False,
        "Bands_match": False,
        "Normalized": False,
        "Normalization_method": None,
        "Warnings": ""
    }

    try:
        with rasterio.open(gt_path) as gt_src:
            gt = gt_src.read().astype(np.float32)
        gt = np.moveaxis(gt, 0, -1)
        gt_shape = gt.shape[:2]
        gt_bands = gt.shape[-1]

        with rasterio.open(sr_path) as sr_src:
            sr = sr_src.read().astype(np.float32)
        sr = np.moveaxis(sr, 0, -1)

        row["sr_orig_min"] = float(np.nanmin(sr))
        row["sr_orig_max"] = float(np.nanmax(sr))
        row["gt_orig_min"] = float(np.nanmin(gt))
        row["gt_orig_max"] = float(np.nanmax(gt))

        # Band match check
        if sr.shape[-1] != gt_bands:
            row["Warnings"] = f"band_mismatch ({sr.shape[-1]} vs {gt_bands})"
            print("⚠️", row["Warnings"])
            return row
        row["Bands_match"] = True

        # Resize if needed
        if sr.shape[:2] != gt_shape:
            sr = resize_image(sr, gt_shape)
            row["Resized"] = True

        # Normalize if needed
        sr_mapped, normalized, method, per_band_stats, warnings = detect_and_normalize(sr, gt, auto_normalize=auto_normalize)
        row["Normalized"] = normalized
        row["Normalization_method"] = method
        if warnings:
            row["Warnings"] = "; ".join(warnings)

        # Compute metrics
        data_range = float(np.nanmax(gt) - np.nanmin(gt) + EPS)

        try:
            row["PSNR"] = float(psnr(gt, sr_mapped, data_range=data_range))
        except Exception as e:
            row["PSNR"] = np.nan
            row["Warnings"] += f"; psnr_error:{e}"

        try:
            row["SSIM"] = float(ssim(gt, sr_mapped, channel_axis=2, data_range=data_range))
        except Exception as e:
            try:
                row["SSIM"] = float(ssim(gt, sr_mapped, multichannel=True, data_range=data_range))
            except Exception as e2:
                row["SSIM"] = np.nan
                row["Warnings"] += f"; ssim_error:{e2}"

        row["RMSE"] = float(np.sqrt(np.mean((gt - sr_mapped) ** 2)))
        row["SAM_rad"] = float(spectral_angle_mapper(gt, sr_mapped))
        row["ERGAS"] = float(ergas(sr_mapped, gt, ratio=ratio))

        print(f"✅ {model_name} | PSNR={row['PSNR']:.3f} SSIM={row['SSIM']:.4f}")

    except Exception as e:
        row["Warnings"] = f"error_processing:{e}"
        print("❌ Error processing", sr_path, e)

    return row
