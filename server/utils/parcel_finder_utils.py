from ..config.constants import TEMP_UPLOADS_PATH
from ..config.minio_client import minioClient, bucket_name
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dateutil.relativedelta import relativedelta
from datetime import datetime
from dotenv import load_dotenv
from minio.error import S3Error
from PIL import Image
from shapely import ops
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from rasterio.mask import mask
from rasterio.merge import merge
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
    geojson_grande = gpd.read_file(GEOMETRY_FILE)
    if geojson_grande.crs != geojson.crs:
        geojson = geojson.to_crs(geojson_grande.crs)

    geojson_grande["geometry"] = geojson_grande["geometry"].apply(extract_polygons_2d)

    interseccion = gpd.overlay(geojson_grande, geojson, how="intersection")

    tiles_zones_list = set(list(interseccion["Name"]))

    return tiles_zones_list

def download_tiles_rgb_bands(utm_zones, year, month):
    """
    Download raw RGB band tiles (.tif) for the given UTM zones and date range.
    """
    year_month_pairs = generate_date_range_last_n_months(year, month)
    image_bands = ["B02_20m", "B03_20m", "B04_20m"]
    downloaded_files = {band: [] for band in image_bands}

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
                            if band in image_bands:
                                download_dir = os.path.join(TEMP_UPLOADS_PATH, str(year), band, month_folder)
                                os.makedirs(download_dir, exist_ok=True)
                                local_file_path = os.path.join(download_dir, f"{zone}.tif")
                                task = executor.submit(download_image_file, minioClient, file, local_file_path)
                                download_tasks.append((task, band, local_file_path))
                except S3Error as exc:
                    print(f"Error when accessing {composites_path}: {exc}")

        for task, band, local_file_path in download_tasks:
            task.result()
            downloaded_files[band].append(local_file_path)
    
    merged_paths = []
    for band, file_list in downloaded_files.items():
        if not file_list:
            continue
        # Get most recent downloaded file
        recent_file = file_list[-1]
        input_dir = os.path.dirname(recent_file)
        # Get month folder name from path
        month_folder = os.path.basename(input_dir)
        month_number = datetime.strptime(month_folder, "%B").month
        merge_path = merge_tifs(input_dir, year, band, month_number)
        if merge_path:
            merged_paths.append(merge_path)

    return merged_paths

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
    Merges all same-band images into one mosaic, reprojecting to a common CRS if needed.
    Arguments:
        input_dir (str): Local directory where band images are stored.
        year (str): Year of the desired image.
        band (str): Band name.
        month_number (str): Month of the desired image (number as string, e.g., "02").
    Returns:
        merged_image_path (str): Local file path to the resulting merged image.
    """
    all_files = reproject_tiles(input_dir)

    # Now merge all files (original or reprojected)
    src_files_to_mosaic = [rasterio.open(f) for f in all_files]
    mosaic, out_transform = merge(src_files_to_mosaic)

    out_meta = src_files_to_mosaic[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform
    })

    out_path = os.path.join(TEMP_UPLOADS_PATH, str(year), band)
    os.makedirs(out_path, exist_ok=True)
    merged_image_path = f"{out_path}/RGB_{year}_{month_number}_{band}.tif"

    with rasterio.open(merged_image_path, "w", **out_meta) as dest:
        dest.write(mosaic)

    # Clean up open files
    for src in src_files_to_mosaic:
        src.close()

    return merged_image_path

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

def rgb(merged_paths):
    """
    Generates RGB composite images from a list of merged band file paths, saves them as GeoTIFF and PNG files, and returns their paths.
    This function groups input file paths by year and month, combines the corresponding red, green, and blue bands into RGB GeoTIFF images, normalizes and applies gamma correction, then saves enlarged PNG images with alpha transparency. It also creates an animated sequence if multiple frames are generated.
    Args:
        merged_paths (list of str): List of file paths to band images, expected to follow a naming convention including year, month, and band identifiers.
    Returns:
        tuple:
            out_dir (str): Output directory where images are saved.
            png_paths (list of str): List of file paths to the generated PNG images.
            rgb_tif_paths (list of tuple): List of tuples containing (GeoTIFF file path, year, month) for each generated RGB composite.
    """

    out_dir = TEMP_UPLOADS_PATH
    png_paths = []
    rgb_tif_paths = []

    grouped = {}
    for file in merged_paths:
        filename = os.path.basename(file)
        filename_no_ext = os.path.splitext(filename)[0]
        filename_parts = filename_no_ext.split("_")
        year = filename_parts[1]
        month_tif = filename_parts[2]
        band = filename_parts[3] + "_" + filename_parts[4]
        id = (year, month_tif)
        if id not in grouped:
            grouped[id] = {}
        grouped[id][band] = file

    for (year, month_number), bands_dict in grouped.items():
        try:
            red_band_02 = bands_dict["B02_20m"]
            green_band_03 = bands_dict["B03_20m"]
            blue_band_04 = bands_dict["B04_20m"]
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
    array_min, array_max = np.percentile(valid_pixels, [2, 99.999])
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
    """Cuts multiple rasters based on a parcel geometry and returns a list of temporary files.

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
        if isinstance(gdf_parcel, dict):
            if "coordinates" not in gdf_parcel:
                raise ValueError(
                    "Invalid parcel geometry dictionary: 'coordinates' key missing."
                )

            parcela_geometry = shape(gdf_parcel)
            parcela_crs = gdf_parcel.get("CRS", {"init": "epsg:4326"})
            gdf_parcel = gpd.GeoDataFrame(geometry=[parcela_geometry], crs=parcela_crs)

        cropped_parcel_masks = []
        valid_files = [f for f in image_paths if f.endswith(f".{format}")]
        if not valid_files:
            raise FileNotFoundError(f"No files found with the .{format} format.")
        
        for image_path in valid_files:
            original_filename = os.path.basename(image_path)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
            with rasterio.open(image_path) as src:
                gdf_parcel = gdf_parcel.to_crs(src.crs)
                if gdf_parcel.is_empty.any():
                    print(f"Parcel geometry is empty for image {image_path}.")
                    continue

                geometries = [gdf_parcel.geometry.iloc[0]]
                out_image, out_transform = mask(src, geometries, crop=True)
                extension = format.lower()
                filename = original_filename.replace(".tif", f"_{geometry_id}.{extension}").replace(".jp2", f"_{geometry_id}.{extension}")
                temp_file = os.path.join(TEMP_UPLOADS_PATH, filename)

                save_raster(out_image, temp_file, src, out_transform, format)
                cropped_parcel_masks.append(temp_file)

        return cropped_parcel_masks

    except FileNotFoundError as e:
        print(str(e))
        raise
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

def get_geojson_data(geometry, metadata):
    
    geojson_data = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": geometry, "properties": metadata}],
    }
    features = geojson_data["features"]
    geometries = [shape(feature["geometry"]) for feature in features]
    properties = [feature["properties"] for feature in features]

    gdf = gpd.GeoDataFrame(properties, geometry=geometries)
    gdf = gdf.set_crs(geojson_data["features"][0]["geometry"].get("CRS", ""))

    return geojson_data, gdf