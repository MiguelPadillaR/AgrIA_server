import cubo
import json
import mlstac
import rasterio
import rioxarray  # needed to access .rio on xarray objects
import torch
import geopandas as gpd

from datetime import datetime, timedelta
from rasterio.transform import from_origin
from rasterio.mask import mask

from .constants import *
from .utils import brighten, get_cloudless_time_indices, save_png
from ...config.constants import RESOLUTION, TEMP_UPLOADS_PATH

lat = 42.465982
lon = -2.292661
now = datetime.today()
look_from = now - timedelta(days=15)
bands = ["B08", "B02", "B03", "B04", "SCL"]  # NIR + RGB + SCL

# --------------------
# Download model
# --------------------
if not os.path.exists(MODEL_DIR) or len(os.listdir(MODEL_DIR)) == 0:
  mlstac.download(
      file="https://huggingface.co/tacofoundation/sen2sr/resolve/main/SEN2SRLite/NonReference_RGBN_x4/mlm.json",
      output_dir= MODEL_DIR,
  )

# --------------------
# Sentinel-2 cube
# --------------------
da = cubo.create(
    lat= lat,
    lon= lon,
    collection="sentinel-2-l2a",
    bands= bands,
    start_date=look_from.strftime("%Y-%m-%d"),
    end_date=now.strftime("%Y-%m-%d"),
    edge_size=128,
    resolution=RESOLUTION,
)

# take cloudless time slice for testing
scl = da.sel(band="SCL")
sample = da.isel(time=get_cloudless_time_indices(scl)[-1])
sample = sample.sel(band=bands[:-1])  # drop SCL band
sample = sample.rio.write_crs("EPSG:4326", inplace=True)  # assign CRS if missing

# --------------------
# Prepare data
# --------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
original_s2_numpy = (sample.compute().to_numpy() / 10_000).astype("float32")
X = torch.from_numpy(original_s2_numpy).float().to(device)
X = torch.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

# --------------------
# Load + run model
# --------------------
model = mlstac.load((MODEL_DIR)).compiled_model(device=device)
superX = model(X[None]).squeeze(0)

# --------------------
# Prepare band order for export
# --------------------
# Original: [NIR, B, G, R] -> reorder to [R, G, B, NIR]
band_order_tif = [3, 2, 1, 0]  # indices in original array
original_s2_reordered = original_s2_numpy[band_order_tif]
superX_np = superX.detach().cpu().numpy()
superX_reordered = superX_np[band_order_tif]

# --------------------
# GeoTIFF export
# --------------------
minx, miny, maxx, maxy = sample.rio.bounds()
res_x, res_y = sample.rio.resolution()
crs_proj = "EPSG:32630"  # projected CRS
transform = from_origin(minx, maxy, abs(res_x), abs(res_y))

# Create TIF output dir
os.makedirs(TIF_DIR, exist_ok=True)

with rasterio.open(
    OG_TIF_FILEPATH, "w",
    driver="GTiff",
    height=original_s2_reordered.shape[1],
    width=original_s2_reordered.shape[2],
    count=original_s2_reordered.shape[0],
    dtype="float32",
    crs=crs_proj,
    transform=transform
) as dst:
    dst.write(original_s2_reordered)

# Super-res (adjust resolution)
scale = superX_reordered.shape[1] / sample.shape[1]
new_res_x = abs(res_x) / scale
new_res_y = abs(res_y) / scale
transform_sr = from_origin(minx, maxy, new_res_x, new_res_y)

with rasterio.open(
    SR_TIF_FILEPATH, "w",
    driver="GTiff",
    height=superX_reordered.shape[1],
    width=superX_reordered.shape[2],
    count=superX_reordered.shape[0],
    dtype="float32",
    crs=crs_proj,
    transform=transform_sr
) as dst:
    dst.write(superX_reordered)

print("✅ Saved original.tif and superres.tif with corrected band order")

# Create PNG output dir
os.makedirs(PNG_DIR, exist_ok=True)

original_s2_reordered = brighten(original_s2_reordered)
superX_reordered = brighten(superX_reordered)

save_png(original_s2_reordered, OG_PNG_FILEPATH)
save_png(superX_reordered, SR_PNG_FILEPATH)

print("✅ Saved PNGs with correct colors")

# --------------------
# Clipping with polygon
# --------------------
raster_path = SR_TIF_FILEPATH

with rasterio.open(raster_path) as src:
    raster_crs = src.crs
    print(f"SR Raster CRS: {raster_crs}")
    gdf = gpd.read_file(GEOJSON_FILEPATH)
    if raster_crs:
        gdf = gdf.to_crs(raster_crs)
        print(f"Reprojected polygon to match raster CRS: {raster_crs}")
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
out_tif_path = TIF_DIR / f"SR_{now.year}_{now.month}.tif"
with rasterio.open(out_tif_path, "w", **out_meta) as dest:
    dest.write(out_image)

# Save clipped PNG
out_png_path= TEMP_UPLOADS_PATH / f"SR_{now.year}_{now.month}.png"
save_png(out_image, out_png_path, False, 1.4, True, 1.6)

print(f"✅ Clipped raster saved to {out_tif_path} and PNG saved to {out_png_path}")
