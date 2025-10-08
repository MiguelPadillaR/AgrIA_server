import rasterio
import numpy as np
import pandas as pd
from skimage.metrics import structural_similarity as ssim, peak_signal_noise_ratio as psnr
from datetime import datetime
import os, glob

from .constants import BM_DATA_DIR, BM_SR_DIR, BM_RES_DIR
from .utils import *

def compare_sr_metrics():
    # Collect all ground truths
    gt_files = sorted(glob.glob(str(BM_DATA_DIR / "*_original.tif")))
    sr_files = sorted(glob.glob(str(BM_SR_DIR / "*.tif")))

    if not gt_files or not sr_files:
        raise FileNotFoundError("Missing ground truth or SR files")

    print(f"Found {len(gt_files)} ground truths and {len(sr_files)} SR images.")

    paired = {}

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

    # Now evaluate
    for ts, files in paired.items():
        gt_path = files["gt"]
        for model_name in ["SEN2SR", "SR4S"]:
            sr_path = files[model_name]
            if not sr_path or not os.path.exists(sr_path):
                print(f"⚠️ Missing {model_name} for timestamp {ts}")
                continue
            print(f"\n🚀 Benchmarking {model_name} for {os.path.basename(gt_path)} ...")
            compute_metrics_for_folder(gt_path, os.path.dirname(sr_path),
                                       output_dir=BM_RES_DIR, ratio=2, auto_normalize=True)

    print("\n✅ Benchmark complete for all available pairs.")

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
