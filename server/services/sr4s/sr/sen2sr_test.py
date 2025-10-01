import mlstac
import torch
import cubo
import numpy as np
import cv2
import matplotlib.pyplot as plt
import rasterio
from rasterio.transform import from_origin
import rioxarray  # needed to access .rio on xarray objects

# --------------------
# Download model
# --------------------
mlstac.download(
    file="https://huggingface.co/tacofoundation/sen2sr/resolve/main/SEN2SRLite/NonReference_RGBN_x4/mlm.json",
    output_dir="model/SEN2SRLite_RGBN",
)

# --------------------
# Sentinel-2 cube
# --------------------
da = cubo.create(
    lat=42.465982,
    lon=-2.292661,
    collection="sentinel-2-l2a",
    bands=["B08", "B02", "B03", "B04"],  # NIR + RGB
    start_date="2025-09-01",
    end_date="2025-09-04",
    edge_size=128,
    resolution=10,
)

# We'll just take the first time slice for testing
sample = da.isel(time=0)
# Make sure the xarray has rioxarray enabled
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
model = mlstac.load("model/SEN2SRLite_RGBN").compiled_model(device=device)
superX = model(X[None]).squeeze(0)

# --------------------
# Visualization prep
# --------------------
rgb_idx = [3, 2, 1]  # R,G,B = B04, B03, B02

og_rgb = np.clip(np.transpose(X[rgb_idx].cpu().numpy(), (1, 2, 0)), 0, 1)
sr_rgb = np.clip(np.transpose(superX[rgb_idx].detach().cpu().numpy(), (1, 2, 0)), 0, 1)

# Brighten both by scaling and clipping
def brighten(img, factor=1.5):
    return np.clip(img * factor, 0, 1)

og_rgb = brighten(og_rgb, 2.5)
sr_rgb = brighten(sr_rgb, 2.5)

# Difference (resize OG to SR size)
og_upscaled = cv2.resize(og_rgb, (sr_rgb.shape[1], sr_rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
diff = np.abs(sr_rgb - og_upscaled)

# --------------------
# Plot for sanity check
# --------------------
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
axes[0].imshow(og_rgb); axes[0].set_title("Original"); axes[0].axis("off")
axes[1].imshow(sr_rgb); axes[1].set_title("Super-Resolved"); axes[1].axis("off")
axes[2].imshow(diff / diff.max()); axes[2].set_title("Difference"); axes[2].axis("off")
plt.tight_layout(); plt.show()

plt.imsave("original.png", og_rgb)
plt.imsave("superres.png", sr_rgb)
plt.imsave("difference.png", diff / diff.max())

# --------------------
# GeoTIFF export
# --------------------

# 1. Extract geoinfo from the xarray sample
minx, miny, maxx, maxy = sample.rio.bounds()
res_x, res_y = sample.rio.resolution()
crs_proj = "EPSG:32630"  # correct projected CRS
transform = from_origin(minx, maxy, abs(res_x), abs(res_y))
print("Sample CRS:", crs_proj)
# 2. Write original (georeferenced) - band order same as original array
transform = from_origin(minx, maxy, abs(res_x), abs(res_y))

with rasterio.open(
    "original.tif", "w",
    driver="GTiff",
    height=original_s2_numpy.shape[1],
    width=original_s2_numpy.shape[2],
    count=original_s2_numpy.shape[0],
    dtype="float32",
    crs=crs_proj,
    transform=transform
) as dst:
    dst.write(original_s2_numpy)

# 3. Write super-res (adjust resolution)
scale = superX.shape[1] / sample.shape[1]
new_res_x = abs(res_x) / scale
new_res_y = abs(res_y) / scale
transform_sr = from_origin(minx, maxy, new_res_x, new_res_y)

superX_np = superX.detach().cpu().numpy()

with rasterio.open(
    "superres.tif", "w",
    driver="GTiff",
    height=superX_np.shape[1],
    width=superX_np.shape[2],
    count=superX_np.shape[0],
    dtype="float32",
    crs=crs_proj,
    transform=transform_sr
) as dst:
    dst.write(superX_np)

print("✅ Saved original.tif and superres.tif with georeferencing.")


import rasterio
from rasterio.mask import mask
import geopandas as gpd
import json

# Paths
raster_path = "superres.tif"
geojson_path = "polygon.geojson"
out_path = "clipped.tif"

with rasterio.open("original.tif") as src:
    raster_crs = src.crs
    print(f"OG Raster CRS: {raster_crs}")
    print("OG Bounds", src.bounds)  # raster bounding box

# 1. Load the raster
with rasterio.open(raster_path) as src:
    raster_crs = src.crs
    print(f"SR Raster CRS: {raster_crs}")
    # 2. Load the polygon
    gdf = gpd.read_file(geojson_path)

    # Ensure the CRS matches the raster
    if raster_crs != None:
      gdf = gdf.to_crs(raster_crs)
      print(f"Reprojected polygon to match raster CRS: {raster_crs}")
    else:
      print("Warning: Raster has no CRS information.")

    print("SR Bounds:", src.bounds)  # raster bounding box
    print(gdf.total_bounds)  # polygon bounding box

    # 3. Convert polygon to GeoJSON dict
    geom = [json.loads(gdf.to_json())["features"][0]["geometry"]]
    
    # 4. Mask the raster with the polygon
    out_image, out_transform = mask(src, geom, crop=True)
    out_meta = src.meta.copy()

# 5. Update metadata
out_meta.update({
    "driver": "GTiff",
    "height": out_image.shape[1],
    "width": out_image.shape[2],
    "transform": out_transform
})

# 6. Save clipped raster
with rasterio.open(out_path, "w", **out_meta) as dest:
    dest.write(out_image)

print(f"✅ Clipped raster saved to {out_path}")



import numpy as np
from PIL import Image

png_path = "clipped.png"
rgb = np.stack([out_image[0], out_image[1], out_image[2]], axis=2)
# Normalize each band
rgb_norm = ((rgb - rgb.min()) / (rgb.max() - rgb.min()) * 255).astype(np.uint8)
Image.fromarray(rgb_norm).save(png_path)

print(f"✅ Saved PNG to {png_path}")
