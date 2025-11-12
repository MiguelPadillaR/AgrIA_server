import math
from pathlib import Path
import re
import shutil
from flask import jsonify
from pyproj import Transformer, CRS

from ..services.sr4s.im.get_image_bands import download_from_sentinel_hub
from ..services.sr4s.sr.get_sr_image import process_directory
from ..services.sr4s.sr.utils import percentile_stretch, set_reflectance_scale
from ..config.constants import ANDALUSIA_TILES, SPAIN_ZONES, TEMP_DIR, SR_BANDS, RESOLUTION, BANDS_DIR, MERGED_BANDS_DIR, MASKS_DIR, SR5M_DIR

from ..config.minio_client import minioClient, bucket_name
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dateutil.relativedelta import relativedelta
from datetime import datetime
from dotenv import load_dotenv
from minio.error import S3Error
from PIL import Image
from shapely import Point, box, ops, unary_union
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape, mapping
from rasterio.mask import mask
from rasterio.merge import merge
from shapely.ops import transform as shapely_transform
from rasterio.warp import calculate_default_transform, reproject, Resampling

import cv2
import geopandas as gpd
import numpy as np
import os
import rasterio

load_dotenv()


GEOMETRY_FILE = os.getenv("GEOMETRY_FILE")

def extract_polygons_2d(geometry):
    if isinstance(geometry, GeometryCollection):
        polygons = [geom for geom in geometry.geoms if isinstance(geom, Polygon)]
        if polygons:
            # return the first polygon if there is only one, otherwise return a MultiPolygon
            return (
                ops.transform(lambda x, y, z=None: (x, y), polygons[0])
                if len(polygons) == 1
                else ops.transform(lambda x, y, z=None: (x, y), MultiPolygon(polygons))
            )
    elif isinstance(geometry, Polygon):
        return ops.transform(lambda x, y, z=None: (x, y), geometry)
    return None

def get_tiles_polygons(geojson):
    if not GEOMETRY_FILE or not os.path.exists(GEOMETRY_FILE):
        raise FileNotFoundError(f"GEOMETRY_FILE is not set or does not exist: {GEOMETRY_FILE}")
    base_geojson = gpd.read_file(GEOMETRY_FILE)
    if base_geojson.crs != geojson.crs:
        geojson = geojson.to_crs(base_geojson.crs)

    base_geojson["geometry"] = base_geojson["geometry"].apply(extract_polygons_2d)

    interseccion = gpd.overlay(base_geojson, geojson, how="intersection")

    tiles_zones_list = set(list(interseccion["Name"]))

    return tiles_zones_list

def download_tile_bands(utm_zones, year, month, bands, geometry):
    """
    Download raw band tiles (.tif) for the given UTM zones and date range.
    """
    year_month_pairs = generate_date_range_last_n_months(year, month)
    downloaded_files = {band: [] for band in bands}
    band_files_list = [] 
    is_zone_in_andalusia =any(zone in ANDALUSIA_TILES for zone in utm_zones)
    set_reflectance_scale(is_zone_in_andalusia)
    
    if is_zone_in_andalusia:
        print("Parcel located in Andalusia...")
        band_files_list = download_from_minio(utm_zones, year_month_pairs, bands)
    else:
        print("Getting parcel outside of Andalusia...")
        # Download image bands using Sentinel Hub
        parcel_center  = shape(geometry).representative_point()
        band_files_list = download_from_sentinel_hub(parcel_center.y, parcel_center.x, f"{year}_{month}")
        for path in band_files_list:
            for band in downloaded_files:
                if band in path:
                    downloaded_files[band].append(path)
    
    return band_files_list[-4:]

def download_from_minio(utm_zones, year_month_pairs, bands):
    # Download image bands from MinIO DB:
    res = []
    download_tasks = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for zone in utm_zones:
            for year, month_folder in year_month_pairs:
                composites_path = f"{zone}/{year}/{month_folder}/composites/"
                try:
                    composites_dir = minioClient.list_objects(bucket_name, prefix=composites_path, recursive=True)
                    for file in composites_dir:
                        if file.object_name.endswith(".tif") and "raw" in file.object_name:
                            band = file.object_name.split("/")[-1].split(".")[0]
                            if band in bands:
                                # Assign and generate local download dir
                                download_dir = BANDS_DIR
                                download_dir.mkdir(parents=True, exist_ok=True)
                                os.makedirs(download_dir, exist_ok=True)
                                # Generate filename
                                month_number = datetime.strptime(month_folder, "%B").month
                                local_file_path = os.path.join(download_dir, f"{year}_{month_number}-{band}.tif")
                                # Set the download file task
                                task = executor.submit(download_image_file, minioClient, file, local_file_path)
                                download_tasks.append((task, local_file_path))
                except S3Error as exc:
                    print(f"Error when accessing {composites_path}: {exc}")
        # Run all download tasks and append resulting local file paths
        for task, local_file_path in download_tasks:
            task.result()
            res.append(local_file_path)
    return res

def generate_date_range_last_n_months(year, month, month_range=2):
    """
    Takes a year and a month and generates a list of tuples with the year and the last N months (including the current month).

    Arguments:
        year (str): Year of the desired image.
        month (str): Month of the desired image (number as string, e.g., "02").
        months_range (int): Number of months before the current one to include. Default is 2

    Returns:
        date_range (list): List of tuples (year, month name).
    """
    current_date = datetime.strptime(f"{year}-{month.zfill(2)}", "%Y-%m")
    start_date = current_date - relativedelta(months=month_range)
    
    date_range = []
    while start_date <= current_date:
        date_range.append((start_date.year, start_date.strftime("%B")))
        start_date += relativedelta(months=1)

    return date_range

def download_image_file(client, file, local_file_path):
    client.fget_object(bucket_name, file.object_name, local_file_path)

def merge_tifs(input_dir, year, band, month_number):
    """
    Merge all GeoTIFF tiles for a band into one mosaic. 
    If only one file is found, copy/re-save it. 
    Returns the merged GeoTIFF path.

    Args:
        input_dir (str): Local directory where band images are stored.
        year (str): Year of the desired image.
        band (str): Band name (e.g., "B02", "B03", "B04", "B08").
        month_number (str): Month of the desired image (e.g., "02").

    Returns:
        str: Local file path to the resulting merged image.
    """
    # Reproject tiles (ensures consistent CRS/res)
    all_files = reproject_tiles(input_dir)
    band_files = [f for f in all_files if band in Path(f).name]

    if not band_files:
        print(f"⚠️ No files found for band {band} in {input_dir}")
        return None

    out_path = MERGED_BANDS_DIR
    os.makedirs(out_path, exist_ok=True)
    merged_image_path = out_path / f"RGB_{year}_{month_number}-{band}.tif"

    # Case 1: Only one file → just copy/re-save
    if len(band_files) == 1:
        with rasterio.open(band_files[0]) as src:
            meta = src.meta.copy()
            with rasterio.open(merged_image_path, "w", **meta) as dst:
                dst.write(src.read())
        return str(merged_image_path)

    # Case 2: Multiple files → mosaic
    src_files = [rasterio.open(f) for f in band_files]
    mosaic, out_transform = merge(src_files)

    out_meta = src_files[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform,
        "count": mosaic.shape[0]  # preserves multi-band mosaics
    })

    with rasterio.open(merged_image_path, "w", **out_meta) as dest:
        dest.write(mosaic)

    # Cleanup
    for src in src_files:
        src.close()

    return str(merged_image_path)

def reproject_tiles(input_dir):
    """
    Reproject tile files to the same Cooridinates Reference System (CRS) if needed.
    Arguments:
        input_dir (`str`): Input directory where the files are
    Returns:
        all_files (list of `str`): list of reporjected / default file paths
    """
    files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith(".tif")]
    if not files:
        print("No .tif files found in:", input_dir)
        return None

    crs_groups = defaultdict(list)

    for f in files:
        with rasterio.open(f) as src:
            print(f"File: {f} CRS: {src.crs}")
            crs_groups[str(src.crs)].append(f)

    # If all files share the same CRS → use directly
    if len(crs_groups) == 1:
        all_files = files
    else:
        print("Multiple CRS detected, reprojection needed...")
        # Pick the CRS of the first file as the target
        with rasterio.open(files[0]) as src:
            target_crs = src.crs

        reprojected_files = []

        for crs, group_files in crs_groups.items():
            for f in group_files:
                with rasterio.open(f) as src:
                    transform, width, height = calculate_default_transform(
                        src.crs, target_crs, src.width, src.height, *src.bounds)
                    kwargs = src.meta.copy()
                    kwargs.update({
                        'crs': target_crs,
                        'transform': transform,
                        'width': width,
                        'height': height
                    })

                    # Create new path for reprojected version
                    reprojected_path = f.replace(".tif", "_reprojected.tif")
                    print(f"Reprojecting {f} → {reprojected_path}")

                    with rasterio.open(reprojected_path, 'w', **kwargs) as dst:
                        for i in range(1, src.count + 1):
                            reproject(
                                source=rasterio.band(src, i),
                                destination=rasterio.band(dst, i),
                                src_transform=src.transform,
                                src_crs=src.crs,
                                dst_transform=transform,
                                dst_crs=target_crs,
                                resampling=Resampling.nearest
                            )
                    reprojected_files.append(reprojected_path)
        all_files = reprojected_files
    return all_files

def get_rgb_composite(cropped_parcel_band_paths, geojson_data):
    """
    Generates RGB composite images from a list of merged band file paths, saves them as GeoTIFF and PNG files, and returns their paths.
    This function groups input file paths by year and month, combines the corresponding red, green, and blue bands into RGB GeoTIFF images, normalizes and applies gamma correction, then saves enlarged PNG images with alpha transparency. It also creates an animated sequence if multiple frames are generated.
    Args:
        cropped_parcel_band_paths (list of str): List of file paths to band images, expected to follow naming convention (`year`_`month_number`-`band`_`RESOLUTION`').
    Returns:
        tuple:
            out_dir (str): Output directory where images are saved.
            png_paths (list of str): List of file paths to the generated PNG images.
            rgb_tif_paths (list of tuple): List of tuples containing (GeoTIFF file path, year, month) for each generated RGB composite.
    """

    out_dir = TEMP_DIR

    # Check for the RBG + B08 bands for L1BSR upscale
    get_sr_image = len(cropped_parcel_band_paths) == 4 and any(SR_BANDS[-1] in path for path in cropped_parcel_band_paths)
    if get_sr_image:
        out_dir = SR5M_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        
    png_paths = []
    rgb_tif_paths = []

    # Group file bands info
    grouped = {}
    for file in cropped_parcel_band_paths:
        # Generate id from filename
        filename = os.path.basename(file)
        filename_no_ext = os.path.splitext(filename)[0]
        filename_parts = re.split(r'[_-]', filename_no_ext)
        year = filename_parts[0]
        month_number = filename_parts[1]
        band = filename_parts[2] + "_" + filename_parts[3]
        id = (year, month_number)
        if id not in grouped:
            grouped[id] = {}
        grouped[id][band] = file

    if get_sr_image:
        # Apply SR upscaling (x10)
        input_dir = Path(cropped_parcel_band_paths[0]).parent
        print(f"\nProcessing {input_dir} directory for SR upscale...\n")
        sr_tif_path = process_directory(input_dir)
        sr_tif = os.path.join(SR5M_DIR, os.path.splitext(os.path.basename(sr_tif_path))[0] + '.tif')
        
        # Crop parcel from SR RGB
        cropped_sr = crop_raster_to_geometry(
            image_path=sr_tif,
            geometry=gpd.GeoDataFrame.from_features(
                geojson_data["features"], crs="EPSG:4326"
            ),
            geometry_id="",
            output_dir=TEMP_DIR,
            fmt="png"
        )

        print(f"SR parcel cropped and saved at: {cropped_sr}")

        png_paths.append(cropped_sr)
    else:
        for (year, month_number), bands_dict in grouped.items():
            try:
                red_band_02 = bands_dict[f"B02_{RESOLUTION}m"]
                green_band_03 = bands_dict[f"B03_{RESOLUTION}m"]
                blue_band_04 = bands_dict[f"B04_{RESOLUTION}m"]
            except KeyError:
                continue

            with rasterio.open(blue_band_04) as src4, \
                rasterio.open(green_band_03) as src3, \
                rasterio.open(red_band_02) as src2:

                red = handle_nodata(src4.read(1), src4.nodata)
                green = handle_nodata(src3.read(1), src3.nodata)
                blue = handle_nodata(src2.read(1), src2.nodata)

                profile = src4.profile
                profile.update(count=3, dtype=rasterio.uint16, nodata=None)
                nombre_tif = os.path.join(out_dir, f"RGB_{year}_{month_number}.tif")

                with rasterio.open(nombre_tif, 'w', **profile) as dst:
                    dst.write(red, 1)
                    dst.write(green, 2)
                    dst.write(blue, 3)

                rgb_tif_paths.append((nombre_tif, year, month_number))

        for rgb_tif_path, year, month_number in rgb_tif_paths:
            with rasterio.open(rgb_tif_path) as src:
                red = handle_nodata(src.read(1), src.nodata)
                green = handle_nodata(src.read(2), src.nodata)
                blue = handle_nodata(src.read(3), src.nodata)

                red_norm = normalize(red)
                green_norm = normalize(green)
                blue_norm = normalize(blue)

                alpha = np.where(
                    (red_norm == 0) & (green_norm == 0) & (blue_norm == 0),
                    0,
                    255
                ).astype(np.uint8)

                rgb_image = np.stack([red_norm, green_norm, blue_norm], axis=-1)
                rgb_image = gamma_correction(rgb_image, gamma=1.5)
                rgba_image = np.dstack([rgb_image, alpha])

                img_pil = Image.fromarray(rgba_image, mode="RGBA")

                # Calculate new size
                width, height = img_pil.size
                scale_factor = max(1, 240 / min(width, height))
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                upscaled_image = img_pil.resize((new_width, new_height), resample=Image.BICUBIC)


                overlay = Image.new("RGBA", upscaled_image.size, (255, 255, 255, 0))
                final_img = Image.alpha_composite(upscaled_image, overlay)

                png_file = os.path.join(out_dir, f"{year}_{month_number}.png")
                final_img.save(png_file)
                png_paths.append(png_file)

    return out_dir, png_paths, rgb_tif_paths
    
def handle_nodata(array, nodata_value):
    """
    Handles null/none data values in arrays
    """
    if nodata_value is not None:
        array = np.where(array == nodata_value, 0, array)
    array = np.where(np.isnan(array), 0, array)
    return array

def normalize(array):
    """
    Normalizes tif images pixel values to 0-255 RGB values
    """
    valid_pixels = array[array > 0]
    if len(valid_pixels) == 0:
        return np.zeros_like(array, dtype=np.uint8)
    array_min, array_max = np.percentile(valid_pixels, [2, 98])
    if array_max - array_min == 0:
        return np.zeros_like(array, dtype=np.uint8)
    norm_array = (array - array_min) / (array_max - array_min)
    norm_array = np.clip(norm_array * 255, 0, 255)
    return norm_array.astype(np.uint8)

def gamma_correction(image, gamma=1.5):
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in np.arange(0, 256)]).astype("uint8")
    return cv2.LUT(image, table)

def save_raster(image, temp_file, src, transform, format):
    """Saves a raster image to a temporary file.

    Args:
        image (numpy.ndarray): The raster image array to save.
        temp_file (str): Path to the temporary file where the image will be saved.
        src (rasterio.io.DatasetReader): The source raster data to extract metadata.
        transform (Affine): The affine transform to apply to the raster.
        format (str): Format to save the file, e.g., 'tif' or 'jp2'.

    Raises:
        Exception: If there is an error saving the raster file.
    """
    try:
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "driver": "GTiff" if format == "tif" else "JP2OpenJPEG",
                "height": image.shape[1],
                "width": image.shape[2],
                "transform": transform,
            }
        )
        with rasterio.open(temp_file, "w", **out_meta) as dest:
            dest.write(image)
    except Exception as e:
        raise Exception(f"Failed to save raster: {str(e)}")

def cut_from_geometry(gdf_parcel, format, image_paths, geometry_id):
    """
    Cuts multiple rasters based on a parcel geometry and returns a list of temporary files.

    Args:
        gdf_parcel (GeoDataFrame or dict): GeoDataFrame containing the geometry, or a dictionary representing the parcel geometry.
        format (str): Format for output raster files, e.g., 'tif' or 'jp2'.
        image_paths (list of str): List of paths to raster files to be cut.

    Returns:
        list: List of file paths to the cropped raster images.

    Raises:
        FileNotFoundError: If no raster files match the format.
        Exception: For other errors during the cutting process.
    """
    try:
        geometry = gdf_parcel
        
        # Check for the RBG + B08 bands for L1BSR upscale
        get_sr_image = len(image_paths) == 4 and any(SR_BANDS[-1] in path for path in image_paths)

        if get_sr_image:
            if geometry:
                geometry = bbox_from_polygon(geometry)
            # TODO:
            # else: 
            #     geometry = get_bbox_from_center(lat, lon, min_size, min_size, RESOLUTION).geojson

        
        # Sanity check
        if isinstance(geometry, dict):
            if "coordinates" not in geometry:
                raise ValueError(
                    "Invalid parcel geometry dictionary: 'coordinates' key missing."
                )
            # Extract geom data
            parcel_geometry = shape(geometry)
            parcel_crs = geometry.get("CRS", {"init": "epsg:4326"})
            geometry = gpd.GeoDataFrame(geometry=[parcel_geometry], crs=parcel_crs)

        cropped_parcel_files = []

        valid_files = [f for f in image_paths if f.endswith(f".{format}")]
        if not valid_files:
            raise FileNotFoundError(f"No files found with the .{format} format.")
        
        # Extract geom mask for each band file
        masks_dir = MASKS_DIR
        cropped_parcel_files = crop_directory(valid_files, geometry, geometry_id, masks_dir)

        return cropped_parcel_files

    except FileNotFoundError as e:
        print(str(e))
        raise
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

def crop_raster_to_geometry(image_path, geometry, geometry_id, output_dir, fmt="tif", target_size = (300, 300)):
    """
    Crop either a single-band or multi-band raster (e.g., Sentinel bands or True Color RGB) to a geometry.

    Args:
        image_path (str | Path): Path to the raster file.
        geometry (GeoDataFrame or shapely object): Crop geometry.
        geometry_id (str): Unique identifier for geometry (added to filename).
        output_dir (str | Path): Directory where cropped file will be saved.
        fmt (str): Output format ("tif" or "png"). Default is "tif".

    Returns:
        str: Path to cropped file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(image_path) as src:
        # Ensure geometry in same CRS
        if hasattr(geometry, "to_crs"):
            geometry = geometry.to_crs(src.crs)

        if geometry.is_empty.any():
            print(f"Parcel geometry is empty for {image_path}")
            return None

        # Rasterio expects list of shapes
        geometries = [geometry.geometry.iloc[0] if hasattr(geometry, "geometry") else geometry]

        # Crop
        out_image, out_transform = mask(src, geometries, crop=True)

        # Prepare output filename
        ext = fmt.lower()
        original_filename = Path(image_path).name
        new_filename = original_filename.replace(".tif", f"_{geometry_id}.{ext}").replace(".jp2", f"_{geometry_id}.{ext}")
        out_path = output_dir / new_filename

        # Save with georeferencing if GeoTIFF
        if fmt.lower() == "tif":
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform
            })
            with rasterio.open(out_path, "w", **out_meta) as dst:
                dst.write(out_image)

        # If PNG, drop CRS and save with Pillow
        elif fmt.lower() == "png":
            # Expecting C,H,W
            if out_image.shape[0] >= 3:  
                red  = out_image[0]  
                green = out_image[1]
                blue   = out_image[2]

                rgb = np.stack([red, green, blue], axis=-1)

                # Stretch to 0–255 for visibility
                rgb_stretched = normalize(rgb)
                rgb_stretched = percentile_stretch(rgb_stretched)

                # Create alpha channel: transparent where all channels are 0
                alpha = np.where(np.all(rgb_stretched == 0, axis=-1), 0, 255).astype(np.uint8)

                # Combine RGB + alpha
                rgba = np.dstack([rgb_stretched, alpha])

                img = Image.fromarray(rgba, mode="RGBA")

                # Resize only if smaller than target_size
                if img.width < target_size[0] or img.height < target_size[1]:
                    scale_w = target_size[0] / img.width
                    scale_h = target_size[1] / img.height
                    scale = max(scale_w, scale_h)
                    new_size = (int(img.width * scale), int(img.height * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

            else:
                # Single-band fallback
                arr = out_image[0]
                img = Image.fromarray(arr.astype(np.uint8))

                # Resize only if smaller than target_size
                if img.width < target_size[0] or img.height < target_size[1]:
                    scale_w = target_size[0] / img.width
                    scale_h = target_size[1] / img.height
                    scale = max(scale_w, scale_h)
                    new_size = (int(img.width * scale), int(img.height * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

            img.save(out_path)
        else:
            raise ValueError(f"Unsupported output format: {fmt}")
        return str(out_path)

def upscale_to_minimum(img, target_size):
    # Current size
    w, h = img.size
    target_w, target_h = target_size

    # Determine scale factor to reach minimum size
    scale_w = target_w / w
    scale_h = target_h / h
    scale = max(scale_w, scale_h)  # use max to ensure both dimensions ≥ target

    if scale > 1:  # only upscale if smaller
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    return img

def crop_directory(valid_files, geometry, geometry_id, output_dir, fmt="tif"):
    """
    Apply crop_raster_to_geometry to all files in a directory.
    Works for both single-band Sentinel bands and multi-band RGB tiffs.
    """
    cropped_files = []
    for image_path in valid_files:
        cropped = crop_raster_to_geometry(image_path, geometry, geometry_id, output_dir, fmt)
        if cropped:
            cropped_files.append(cropped)
    return cropped_files

def get_geojson_data(geometry, metadata):
    
    geojson_data = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": geometry, "properties": metadata}],
    }
    features = geojson_data["features"]
    geometries = [shape(feature["geometry"]) for feature in features]
    properties = [feature["properties"] for feature in features]
    gdf = gpd.GeoDataFrame(properties, geometry=geometries)
    gdf = gdf.set_crs("EPSG:4326")  # Set CRS explicitly

    return geojson_data, gdf

def find_nearest_feature_to_point(feature_collection: dict, lat: float, lng: float) -> dict | None:
    """
    Finds the feature in the GeoJSON FeatureCollection nearest to a given point.

    Args:
        feature_collection (dict): GeoJSON FeatureCollection.
        lat (float): Latitude of the point.
        lng (float): Longitude of the point.

    Returns:
        dict or None: The closest feature (unaltered except geometry transformed to EPSG:4326), or None.
    """
    point = Point(lng, lat)
    min_dist = float("inf")
    closest_feature = None

    # Parse current CRS and set up transformer to EPSG:4326
    current_crs = f"{feature_collection['crs']['type']}:{feature_collection['crs']['properties']['code']}"
    transformer = Transformer.from_crs(current_crs, "EPSG:4326", always_xy=True)

    for feature in feature_collection.get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue

        shapely_geom = shape(geom)
        transformed_geom = shapely_transform(lambda x, y, z=None: transformer.transform(x, y), shapely_geom)

        dist = transformed_geom.distance(point)
        if dist < min_dist:
            min_dist = dist
            closest_feature = {
                **feature,
                "geometry": geojson_with_crs(mapping(transformed_geom), "epsg:4326")
            }

    return closest_feature

def geojson_with_crs(geometry_dict: dict, crs: str = "epsg:4326") -> dict:
    """
    Adds a CRS field to a geometry dict, mimicking custom GeoJSON with CRS.
    """
    geometry_dict["CRS"] = crs
    return geometry_dict

def merge_and_convert_to_geometry(feature_collection: dict) -> dict:
    """
    Takes a set of FeatureCollection features and generates a single geometry multipolygon object that contains all of the features.
    """
    features = feature_collection.get("features", [])
    if not features:
        raise ValueError("FeatureCollection contains no features.")

    # Setup coordinate transformer: EPSG:3857 ➜ EPSG:4326
    current_crs = f"{feature_collection['crs']['type']}:{feature_collection['crs']['properties']['code']}"
    transformer = Transformer.from_crs(current_crs, "EPSG:4326", always_xy=True)

    # Step 1: Convert each polygon from GeoJSON to shapely geometry
    polygons = []
    for feature in features:
        geom = shape(feature["geometry"])  # Still in 3857
        # Transform coordinates to 4326
        transformed = shapely_transform(lambda x, y, z= None: transformer.transform(x, y), geom)
        polygons.append(transformed)

    # Step 2: Merge/dissolve all polygons
    merged = unary_union(polygons)

    # Step 3: Return as plain geometry dict (not Feature or FeatureCollection)
    del transformer
    return mapping(merged) 

def reset_dir(dir: Path | str):
    # Clear uploaded files and dirs
    if os.path.exists(dir):
        for file in os.listdir(dir):
            file_path = os.path.join(os.getcwd(), dir, file)
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

def check_cadastral_data(cadastral_reference: str, province: str, municipality: str, polygon: str, parcel_id: str):
    """
    Checks cadastral data and handles cadastral reference assignment/generation.
    If no cadastral reference is provided, it generates one from the location data.
    
    Arguments:
        cadastral_reference (str): Alphanumerical 20-character long cadastral reference.
        province (str): Province data. ID-NAME format.
        municipality (str): Municipality data. ID-NAME format.
        polygon (str): Polygon ID. Max: 3 digits.
        parcel_id (str): Parcel ID. Max: 5 digits.

    Returns:
        cadastral_reference (str) 
    """
    if not cadastral_reference:
        if not province:
            return jsonify({'error': 'No cadastral reference nor parcel address location data provided.'}), 400
        else:
            # Build cadastral reference
            cadastral_reference = build_cadastral_reference(province, municipality, polygon, parcel_id)
            print("cadastral_reference", cadastral_reference)
    return cadastral_reference

def build_cadastral_reference(province: str, municipality: str, polygon: str, parcel_id: str):
    """
    Generates a valid RURAL cadastral reference with calculated control characters.
    
    Arguments:
        province (str): Province data. ID-NAME format.
        municipality (str): Municipality data. ID-NAME format.
        polygon (str): Polygon ID. Max: 3 digits.
        parcel_id (str): Parcel ID. Max: 5 digits.

    Returns:
        cadastral_reference (str) 
    """

    # --- 1. Prepare base components ---
    # Province (2 chars)
    prov = province.split('-')[0].zfill(2)

    # Municipality (3 chars)
    muni = municipality.split('-')[0].zfill(3)

    # Section (1 char) -> Use non-digit (e.g., "X") to ensure RURAL
    section = "X"

    # Polygon (3 chars)
    poly = str(polygon).zfill(3)

    # Parcel (5 chars)
    parcel = str(parcel_id).zfill(5)

    # ID (4 chars) -> usually zero unless you have sub-parcel identifiers
    parcel_id_4 = "0000"

    # --- 2. Combine without control characters ---
    partial_ref = prov + muni + section + poly + parcel + parcel_id_4  # 18 chars

    # --- 3. Calculate control characters (positions 19-20) ---
    res = "MQWERTYUIOPASDFGHJKLBZX"
    pos = [13, 15, 12, 5, 4, 17, 9, 21, 3, 7, 1]

    separated_ref = list(partial_ref)

    sum_pd1 = 0
    sum_sd2 = 0
    mixt1 = 0

    # First 7 characters
    for i in range(7):
        ch = separated_ref[i]
        if ch.isdigit():
            sum_pd1 += pos[i] * (ord(ch) - 48)
        else:
            sum_pd1 += pos[i] * ((ord(ch) - 63) if ord(ch) > 78 else (ord(ch) - 64))

    # Next 7 characters
    for i in range(7):
        ch = separated_ref[i + 7]
        if ch.isdigit():
            sum_sd2 += pos[i] * (ord(ch) - 48)
        else:
            sum_sd2 += pos[i] * ((ord(ch) - 63) if ord(ch) > 78 else (ord(ch) - 64))

    # Mixt calculation (last 4 digits before control)
    for i in range(4):
        mixt1 += pos[i + 7] * (ord(separated_ref[i + 14]) - 48)

    code1 = res[(sum_pd1 + mixt1) % 23]
    code2 = res[(sum_sd2 + mixt1) % 23]

    # --- 4. Final cadastral reference ---
    cadastral_reference = partial_ref + code1 + code2

    print("FINAL CADASTRAL REF:", cadastral_reference)
    return cadastral_reference

def bbox_from_polygon(polygon_geojson: dict, resolution_m: int = RESOLUTION, min_px: int=-1 ):
    """
    Given a polygon, return a bbox geometry in EPSG:4326 that is centered
    on the polygon centroid, fully contains it, and ensures at least
    min_px x min_px pixels at the given resolution.

    Args:
        polygon_geojson (dict): Polygon in GeoJSON format (must be EPSG:4326).
        resolution_m (float): Desired resolution in meters per pixel (default 10m/px).
        min_px (int): Minimum size in pixels for bbox width and height. Default: px for bbox that contains `polygon_geojson`.

    Returns:
        dict: GeoJSON geometry for the expanded bbox in EPSG:4326 (lists instead of tuples).
    """
    min_px = polygon_pixel_size(polygon_geojson) if min_px < 0 else min_px
    poly = shape(polygon_geojson)
    centroid = poly.centroid
    minx, miny, maxx, maxy = poly.bounds

    # --- Current polygon size in meters ---
    mean_lat = centroid.y
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(mean_lat))

    width_m = (maxx - minx) * meters_per_deg_lon
    height_m = (maxy - miny) * meters_per_deg_lat

    # --- Required size in meters ---
    min_size_m = min_px * resolution_m
    width_needed_m = max(width_m, min_size_m)
    height_needed_m = max(height_m, min_size_m)

    # --- Convert back to degrees ---
    half_width_deg = (width_needed_m / 2) / meters_per_deg_lon
    half_height_deg = (height_needed_m / 2) / meters_per_deg_lat

    # --- Center on polygon centroid ---
    cx, cy = centroid.x, centroid.y
    minx_exp = cx - half_width_deg
    maxx_exp = cx + half_width_deg
    miny_exp = cy - half_height_deg
    maxy_exp = cy + half_height_deg

    expanded_bbox = box(minx_exp, miny_exp, maxx_exp, maxy_exp)

    # --- Ensure coordinates are lists, not tuples ---
    geom = mapping(expanded_bbox)
    geom["coordinates"] = [
        [list(coord) for coord in ring]
        for ring in geom["coordinates"]
    ]
    geom["CRS"] = guess_crs_from_coords(geom["coordinates"][0])

    return geom

def guess_crs_from_coords(coords):
    xs = [pt[0] for pt in coords]
    ys = [pt[1] for pt in coords]
    
    if all(-180 <= x <= 180 for x in xs) and all(-90 <= y <= 90 for y in ys):
        return "EPSG:4326"  # Lat/lon in degrees
    if all(abs(x) < 20000000 and abs(y) < 20000000 for x, y in zip(xs, ys)):
        return "EPSG:3857"  # Web Mercator
    if all(100000 < x < 1000000 and 0 < y < 10000000 for x, y in zip(xs, ys)):
        return "UTM or national CRS (needs region)"
    return "Unknown"

def polygon_pixel_size(geojson_polygon, resolution=RESOLUTION):
    """
    Compute pixel size (width, height) and max dimension for a polygon and resolution.

    Args:
        geojson_polygon (dict): GeoJSON polygon in EPSG:4326.
        resolution (int | float): Pixel resolution in meters.

    Returns:
        (width_px, height_px, max_dim_px)
    """
    # Load polygon
    poly = shape(geojson_polygon)

    # Put into GeoDataFrame with EPSG:4326
    gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")

    # Pick appropriate UTM zone for reprojection
    centroid = gdf.geometry.iloc[0].centroid
    utm_zone = int((centroid.x + 180) // 6) + 1
    if centroid.y >= 0:
        utm_crs = CRS.from_epsg(32600 + utm_zone)  # Northern Hemisphere
    else:
        utm_crs = CRS.from_epsg(32700 + utm_zone)  # Southern Hemisphere

    # Reproject polygon
    gdf_utm = gdf.to_crs(utm_crs)

    # Get bounds in meters
    minx, miny, maxx, maxy = gdf_utm.total_bounds

    # Define offset (in meters)
    offset_m = resolution * 10 # 10 pixels buffer

    # Expand bounds equally in all directions
    minx = minx - offset_m
    miny = miny - offset_m
    maxx = maxx + offset_m
    maxy = maxy + offset_m

    # Now recalculate width/height with buffer
    width_m = maxx - minx
    height_m = maxy - miny

    # Convert to pixels
    width_px = int(width_m / resolution)
    height_px = int(height_m / resolution)
    max_dim_px = max(width_px, height_px)

    return max_dim_px

def is_coord_in_zones(lon: float, lat: float, zones_json: dict = SPAIN_ZONES) -> str | None:
    """
    Checks if a (lon, lat) coordinate falls within any given zone's bounding box.

    Args:
        lon (float): Longitude in decimal degrees
        lat (float): Latitude in decimal degrees
        zones_json (dict): Dictionary with "zones" list, each containing "bbox"

    Returns:
        bool: Whether the coordinates are within any of the given zones.
    """
    is_in_zone = False
    zones_list = zones_json["zones"]
    i = 0
    while not is_in_zone and i < len(zones_list):
        zone = zones_list[i]
        min_lon, min_lat, max_lon, max_lat = zone["bbox"]
        is_in_zone = min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
        i += 1
    return is_in_zone
