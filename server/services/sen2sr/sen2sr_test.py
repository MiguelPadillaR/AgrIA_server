import time
import cubo
import json
import cv2
import mlstac
import rasterio
import rioxarray  # needed to access .rio on xarray objects
import torch
import geopandas as gpd

from datetime import datetime, timedelta
from rasterio.mask import mask

from .constants import *
from .utils import save_to_png, save_to_tif, get_cloudless_time_indices, make_comparison_grid, reorder_bands, save_png
from ...config.constants import RESOLUTION, TEMP_UPLOADS_PATH

def get_sr_image(lat: float, lon: float, bands: list, start_date: str, end_date: str):
    # Download model
    if not os.path.exists(MODEL_DIR) or len(os.listdir(MODEL_DIR)) == 0:
        mlstac.download(
            file="https://huggingface.co/tacofoundation/sen2sr/resolve/main/SEN2SRLite/NonReference_RGBN_x4/mlm.json",
            output_dir= MODEL_DIR,
        )

    # Prepare data
    cloudless_image_data = download_sentinel_cubo(lat, lon, bands, start_date, end_date)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    original_s2_numpy = (cloudless_image_data.compute().to_numpy() / 10_000).astype("float32")
    X = torch.from_numpy(original_s2_numpy).float().to(device)
    X = torch.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Load + run model
    model = mlstac.load((MODEL_DIR)).compiled_model(device=device)
    superX = model(X[None]).squeeze(0)
    
    # Reorder bands ( [NIR, B, G, R] -> [R, G, B, NIR])
    original_s2_reordered, superX_reordered = reorder_bands(original_s2_numpy, superX)
    
    # Save original and super-res images in TIF & PNG
    save_to_tif(original_s2_reordered, OG_TIF_FILEPATH, cloudless_image_data)
    save_to_tif(superX_reordered, SR_TIF_FILEPATH, cloudless_image_data, True)

    save_to_png(original_s2_reordered, OG_PNG_FILEPATH)
    save_to_png(superX_reordered, SR_PNG_FILEPATH)

    # Make comparison grid TODO
    # make_comparison_grid(original_s2_numpy, superX)

    # Get and save cropped sr parcel image
    sr_image_filepath = crop_parcel_from_sr_tif(SR_TIF_FILEPATH)
    return str(sr_image_filepath)
# --------------------
# Sentinel-2 cube
# --------------------
def download_sentinel_cubo(lat: float, lon: float, bands: list, start_date: str, end_date: str, cloud_threshold: float = 0.01):
    da = cubo.create(
        lat= lat,
        lon= lon,
        collection="sentinel-2-l2a",
        bands= bands,
        start_date=start_date,
        end_date=end_date,
        edge_size=128,
        resolution=RESOLUTION,
    )

    # Take cloudless time slices
    scl = da.sel(band="SCL")
    cloudless_image_data = da.isel(time=get_cloudless_time_indices(scl, cloud_threshold)[-1])  # get most recent image
    cloudless_image_data = cloudless_image_data.sel(band=bands[:-1])  # drop SCL band
    cloudless_image_data = cloudless_image_data.rio.write_crs("EPSG:32630", inplace=True)  # assign CRS if missing
    
    return cloudless_image_data

# --------------------
# Cropping SR parcel with polygon
# --------------------
def crop_parcel_from_sr_tif(raster_path:str): 

    with rasterio.open(raster_path) as src:
        
        raster_crs = src.crs
        print(f"SR Raster CRS: {raster_crs}")
        gdf = gpd.read_file(GEOJSON_FILEPATH)
        if raster_crs:
            gdf = gdf.to_crs(raster_crs)
            print(f"Reprojected polygon to match raster CRS: {raster_crs}")

        # Get parcel's geom and apply mask on SR image
        geom = [json.loads(gdf.to_json())["features"][0]["geometry"]]
        out_image, out_transform = mask(src, geom, crop=True)
        out_meta = src.meta.copy()

    # Update TIF metadata
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform
    })

    # Save cropped TIF
    now =datetime.today()
    out_tif_path = TIF_DIR / f"SR_{now.year}_{now.month}.tif"
    with rasterio.open(out_tif_path, "w", **out_meta) as dest:
        dest.write(out_image)

    # Save cropped PNG
    out_png_path= TEMP_UPLOADS_PATH / f"SR_{now.year}_{now.month}.png"
    save_png(out_image, out_png_path, False, 1.4, True, 1.6)

    print(f"✅ Clipped raster saved to {out_tif_path} and PNG saved to {out_png_path}")
    
    return out_png_path


if __name__ == "__main__":
    lat, lon = 42.465774, -2.292634

    delta = 15
    now = datetime.today().strftime("%Y-%m-%d")
    look_from = (datetime.today() - timedelta(days=delta)).strftime("%Y-%m-%d")
    
    start_time = time.time()
    get_sr_image(lat, lon, BANDS, look_from, now)
    finish_time = time.time()
    print(f"Total time:\t{(finish_time - start_time)/60:.1f} minutes")