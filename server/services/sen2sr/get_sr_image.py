import time
import cubo
import json
import mlstac
import rasterio
import rioxarray  # needed to access .rio on xarray objects
import sen2sr
import torch
import geopandas as gpd
import numpy as np

from datetime import datetime, timedelta
from rasterio.mask import mask

from .constants import *
from .utils import lonlat_to_utm_epsg, save_to_png, save_to_tif, get_cloudless_time_indices, make_pixel_faithful_comparison, reorder_bands
from ...config.constants import RESOLUTION, TEMP_DIR

def get_sr_image(lat: float, lon: float, bands: list, start_date: str, end_date: str, size: int):
    """
    Get SR image from downloaded Sentinel's imagery data and load up SEN2SR model from HuggingFace to Super-Resolve it
    Arguments:
        lat (float): Latitude component
        lat (float): Longitude component
        bands (list): List of bands (`B02`, `B03`, `B04`, `B08` and `SCL`)
        start_date (str): Intial date in search range
        end_date (str): Final date in search range
        size (int): Image size in px.
    Returns:
        sr_image_filepath (str): Local filepath to SR image.
    """
    try:
        # Ensure sizeis right (minimum for SEN2SR)
        print(f"Image size {size}x{size}px")
        # Download model
        if not os.path.exists(MODEL_DIR) or len(os.listdir(MODEL_DIR)) == 0:
            mlstac.download(
                file="https://huggingface.co/tacofoundation/sen2sr/resolve/main/SEN2SRLite/NonReference_RGBN_x4/mlm.json",
                output_dir= MODEL_DIR,
            )
       
        # Prepare data
        crs = lonlat_to_utm_epsg(lon, lat)
        cloudless_image_data, sample_date = download_sentinel_cubo(lat, lon, bands, start_date, end_date, size, crs)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        original_s2_numpy = (cloudless_image_data.compute().to_numpy() / 10_000).astype("float32")
        X = torch.from_numpy(original_s2_numpy).float().to(device)
        X = torch.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Load
        model = mlstac.load((MODEL_DIR)).compiled_model(device=device)
        
        # Apply model for normal or large size images
        if  size <= 128:
            superX = model(X[None]).squeeze(0)
        else:
            superX = sen2sr.predict_large(
                model=model,
                X=X, # The input tensor
                overlap=32, # The overlap between the patches
            )

        # Reorder bands ( [NIR, B, G, R] -> [R, G, B, NIR])
        original_s2_reordered, superX_reordered = reorder_bands(original_s2_numpy, superX)
        
        # Save original and super-res images in TIF & PNG
        save_to_tif(original_s2_reordered, OG_TIF_FILEPATH, cloudless_image_data, crs)
        save_to_tif(superX_reordered, SR_TIF_FILEPATH, cloudless_image_data, crs)

        save_to_png(original_s2_reordered, OG_PNG_FILEPATH, lat)
        save_to_png(superX_reordered, SR_PNG_FILEPATH, lat)

        # Make comparison grid
        make_pixel_faithful_comparison(original_s2_reordered, superX_reordered)

        # Get and save cropped sr parcel image
        sr_image_filepath = str(crop_parcel_from_sr_tif(SR_TIF_FILEPATH, sample_date))
        return sr_image_filepath
    except Exception as e:
        print(f"An error occurred (get_sr_image SEN2SR): {str(e)}")
        raise

# --------------------
# Sentinel-2 cube
# --------------------
def download_sentinel_cubo(lat: float, lon: float, bands: list, start_date: str, end_date: str, size: int, crs: str, cloud_threshold: float = 0.01, max_retries: int = 3, retry_days_shift: int = 15):
    """
    Download Sentinel's imagery data cubo and uses SCL band to filter the least cloudy data within date range.
    Arguments:
        lat (float): Latitude component
        lat (float): Longitude component
        bands (list): List of bands (`B02`, `B03`, `B04`, `B08` and `SCL`)
        start_date (str): Intial date in search range
        end_date (str): Final date in search range
        size (int): Image size in px.
        crs (str): Coordinate Reference System for the image
        cloud_threshold (float): Tolerated cloud density percentage

    Returns:
        cloudless_image_data (array): Cloudless image data array
    """
    for attempt in range(max_retries):
        try:
            print(f"🌍 Attempt {attempt+1}/{max_retries}: {start_date} → {end_date}")
            
            da = cubo.create(
                lat=lat,
                lon=lon,
                collection="sentinel-2-l2a",
                bands=bands,
                start_date=start_date,
                end_date=end_date,
                edge_size=size,
                resolution=RESOLUTION,
            )

            # Find cloudless time index
            scl = da.sel(band="SCL")
            cloudless_date = get_cloudless_time_indices(scl, cloud_threshold)[-1]
            cloudless_image_data = da.isel(time=cloudless_date).sel(band=bands[:-1])  # drop SCL band

            # Get acquisition date and reproject
            acq_date = cloudless_image_data["time"].values
            acq_date_str = np.datetime_as_string(acq_date, unit='D')
            cloudless_image_data = cloudless_image_data.rio.write_crs(crs).rio.reproject(crs)

            print(f"☁️ Cloudless image found on {acq_date_str}!")
            return cloudless_image_data, str(acq_date_str)

        except ValueError as e:
            print(f"⚠️ {e}")
            if attempt < max_retries - 1:
                # Shift the date range backwards by `retry_days_shift` days
                new_start = datetime.fromisoformat(start_date) - timedelta(days=retry_days_shift)
                new_end = datetime.fromisoformat(end_date) - timedelta(days=retry_days_shift)
                start_date, end_date = new_start.strftime("%Y-%m-%d"), new_end.strftime("%Y-%m-%d")
                print(f"🔁 Retrying with earlier range: {start_date} → {end_date}")
                continue
            else:
                print("❌ No valid images found after all retries.")
                raise

# --------------------
# Cropping SR parcel with polygon
# --------------------
def crop_parcel_from_sr_tif(raster_path:str, date): 
    """
    Crops the parcel from the SR image, using the stored parcel's geometry and`rasterio`
    Arguments:
        raster_path (str): Path to uncropped SR image.
    Returns:
        out_png_path (str): Path to cropped SR parcel image
    """
    with rasterio.open(raster_path) as src:
        
        raster_crs = src.crs
        print(f"SR Raster CRS: {raster_crs}")
        gdf = gpd.read_file(GEOJSON_FILEPATH)
        gdf = gpd.read_file(GEOJSON_FILEPATH)
        print("Original GeoJSON CRS:", gdf.crs)
        print("Original polygon bounds:", gdf.total_bounds)
        if raster_crs:
            gdf = gdf.to_crs(raster_crs)
            gdf["geometry"] = gdf["geometry"].buffer(1)
            print(f"Reprojected polygon to match raster CRS: {raster_crs}")
        print("Raster bounds:", src.bounds)
        print("Raster CRS:", src.crs)
        print("Polygon bounds:", gdf.total_bounds)

        # Get parcel's geom and apply mask on SR image
        print("Cropping parcel's geometry from raster...")
        geom = [json.loads(gdf.to_json())["features"][0]["geometry"]]
        out_image, out_transform = mask(src, geom, crop=True)
        out_meta = src.meta.copy()
        print("Cropping successful!")

    # Update TIF metadata
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform
    })

    # Save cropped TIF & PNG
    year, month, day = date.split("-")
    filename = f"SR_{year}-{month}-{day}"

    out_tif_path = TIF_DIR / f"{filename}.tif"
    with rasterio.open(out_tif_path, "w", **out_meta) as dest:
        dest.write(out_image)

    out_png_path= TEMP_DIR / f"{filename}.png"
    save_to_png(out_image, out_png_path, apply_gamma_correction=True)

    print(f"✅ Clipped raster saved to {out_tif_path} and PNG saved to {out_png_path}")
    
    return out_png_path


if __name__ == "__main__":
    lat, lon = 42.465774, -2.292634
    # lat, lon = 46.256440, 2.315916

    delta = 20
    now = datetime.today().strftime("%Y-%m-%d")
    look_from = (datetime.today() - timedelta(days=delta)).strftime("%Y-%m-%d")
    
    start_time = time.time()
    get_sr_image(lat, lon, BANDS, look_from, now, 150)
    finish_time = time.time()
    print(f"Total time:\t{(finish_time - start_time)/60:.1f} minutes")