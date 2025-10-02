import time
import cubo
import json
import mlstac
import rasterio
import rioxarray  # needed to access .rio on xarray objects
import torch
import geopandas as gpd

from datetime import datetime, timedelta
from rasterio.mask import mask

from .constants import *
from .utils import export_to_png, export_to_tif, get_cloudless_time_indices, reorder_bands, save_png
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
    
    # Reorder bands    
    original_s2_reordered, superX_reordered = reorder_bands(original_s2_numpy, superX)
    
    # Save original and super-res images
    export_to_tif(original_s2_reordered, superX_reordered, cloudless_image_data)
    export_to_png(original_s2_reordered, OG_PNG_FILEPATH)
    export_to_png(superX_reordered, SR_PNG_FILEPATH)

    # Get and save cropped sr parcel image
    crop_parcel_from_sr_tif(SR_TIF_FILEPATH)

# --------------------
# Sentinel-2 cube
# --------------------
def download_sentinel_cubo(lat: float, lon: float, bands: list, start_date: str, end_date: str):
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
    sample = da.isel(time=get_cloudless_time_indices(scl)[-1])  # get most recent image
    sample = sample.sel(band=bands[:-1])  # drop SCL band
    sample = sample.rio.write_crs("EPSG:32630", inplace=True)  # assign CRS if missing
    
    return sample

# --------------------
# Clipping with polygon
# --------------------
def crop_parcel_from_sr_tif(raster_path:str): 

    with rasterio.open(raster_path) as src:
        
        raster_crs = src.crs
        print(f"SR Raster CRS: {raster_crs}")
        gdf = gpd.read_file(GEOJSON_FILEPATH)
        if raster_crs:
            gdf = gdf.to_crs(raster_crs)
            print(f"Reprojected polygon to match raster CRS: {raster_crs}")
        print("Raster bounds:", src.bounds)
        print("Polygon bounds:", gdf.total_bounds)
        geom = [json.loads(gdf.to_json())["features"][0]["geometry"]]
        out_image, out_transform = mask(src, geom, crop=True)
        out_meta = src.meta.copy()

    # Update metadata
    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform
    })

    # Save clipped TIF
    now =datetime.today()
    out_tif_path = TIF_DIR / f"SR_{now.year}_{now.month}.tif"
    with rasterio.open(out_tif_path, "w", **out_meta) as dest:
        dest.write(out_image)

    # Save clipped PNG
    out_png_path= TEMP_UPLOADS_PATH / f"SR_{now.year}_{now.month}.png"
    save_png(out_image, out_png_path, False, 1.4, True, 1.6)

    print(f"✅ Clipped raster saved to {out_tif_path} and PNG saved to {out_png_path}")


if __name__ == "__main__":
    lat, lon = 42.465774, -2.292634
    bands = ["B08", "B02", "B03", "B04", "SCL"]  # NIR + RGB + SCL
    
    delta = 15
    now = datetime.today().strftime("%Y-%m-%d")
    look_from = (datetime.today() - timedelta(days=delta)).strftime("%Y-%m-%d")
    
    start_time = time.time()
    get_sr_image(lat, lon, bands, look_from, now)
    finish_time = time.time()
    print(f"Total time:\t{(finish_time - start_time)/60:.1f} minutes")