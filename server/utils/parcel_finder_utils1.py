from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import os
import tempfile
from dateutil.relativedelta import relativedelta
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
import geopandas as gpd
from shapely import ops
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
import rasterio
from rasterio.mask import mask

from ..config.constants import TEMP_UPLOADS_PATH

####
load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
bucket_name = os.getenv("bucket_name")

minioClient = Minio(
    endpoint=MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False,
)
####

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
    geojson_grande = gpd.read_file(
        "./S2A_OPER_GIP_TILPAR_MPC__20151209T095117_V20150622T000000_21000101T000000_B00.kml"
    )
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

    return downloaded_files

def download_tile_rgb_images(utm_zones, year, month):
    """
    Download and merge RGB band tiles (.tif) into one image mosaic per band for later parcel clipping.
    Returns list of paths to merged B02, B03, B04 images.
    """
    year_month_pairs = generate_date_range_last_n_months(year, month)
    image_bands = ["B02_20m", "B03_20m", "B04_20m"]
    merged_paths = []

    download_tasks = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for zone in utm_zones:
            for year, month_folder in year_month_pairs:
                composites_path = f"{zone}/{year}/{month_folder}/composites/"
                try:
                    files_list = minioClient.list_objects(bucket_name, prefix=composites_path, recursive=True)
                    for file in files_list:
                        if file.object_name.endswith(".tif") and "raw" in file.object_name:
                            band = file.object_name.split("/")[-1].split(".")[0]
                            if band in image_bands:
                                download_dir = os.path.join(TEMP_UPLOADS_PATH, str(year), band, month_folder)
                                os.makedirs(download_dir, exist_ok=True)
                                local_file_path = os.path.join(download_dir, f"{zone}.tif")
                                task = executor.submit(download_image_file, minioClient, file, local_file_path)
                                download_tasks.append(task)
                except S3Error as exc:
                    print(f"Error when accessing {composites_path}: {exc}")

        for task in as_completed(download_tasks):
            task.result()

    # Only use the most recent year/month combo that has data
    for year, month_folder in year_month_pairs:
        all_exist = True
        for band in image_bands:
            band_folder = os.path.join(TEMP_UPLOADS_PATH, str(year), band, month_folder)
            if not os.path.exists(band_folder) or not os.listdir(band_folder):
                all_exist = False
                break

        if all_exist:
            for band in image_bands:
                band_folder = os.path.join(TEMP_UPLOADS_PATH, str(year), band, month_folder)
                merge_path = merge_tifs(band_folder, year, band, month_folder)
                if merge_path:
                    merged_paths.append(merge_path)
            break  # Stop after first full match

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
    Merges all red, green and blue band images into one, creating an RGB image.
    Arguments:
        input_dir (str): Local directory where band images are stored.
        year (str): Year of the desired image.
        band (str): Band name.
        month_number (str): Month of the desired image (number as string, e.g., "02").
    Returns:
        merged_image_path (str): Local file path to the resulting merged image.

    """
    files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith(".tif")]
    if not files:
        return None
    mosaic, out_transform = rasterio.merge.merge([rasterio.open(f) for f in files])
    out_meta = rasterio.open(files[0]).meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform
    })
    out_path = f"data/merge/{year}/{band}"
    os.makedirs(out_path, exist_ok=True)
    merged_image_path = f"{out_path}/RGB_{year}_{month_number}_{band}.tif"
    with rasterio.open(merged_image_path, "w", **out_meta) as dest:
        dest.write(mosaic)
    return merged_image_path

## Different file

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

        cropped_images = []
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
                temp_file = os.path.join(tempfile.gettempdir(), filename)

                save_raster(out_image, temp_file, src, out_transform, format)
                cropped_images.append(temp_file)

        return cropped_images

    except FileNotFoundError as e:
        print(str(e))
        raise
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise

## Different file

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