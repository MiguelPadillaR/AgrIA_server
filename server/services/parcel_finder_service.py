from datetime import datetime, timedelta
import json
import time
import os
import traceback

from flask import abort
from .sigpac_tools_v2.find import find_from_cadastral_registry
from .sigpac_tools_v2.locate import  generate_cadastral_ref_from_coords

from ..benchmark.sr.compare_sr_metrics import compare_sr_metrics

from ..benchmark.sr.constants import BM_DATA_DIR, BM_RES_DIR

from .sen2sr.utils import is_in_spain
from .sen2sr.get_sr_image import get_sr_image
from .sen2sr.constants import BANDS, GEOJSON_FILEPATH
from ..services.sr4s.im.utils import get_bbox_from_center

from ..config.constants import GET_SR_BENCHMARK, SEN2SR_SR_DIR, SR_BANDS, RESOLUTION
from ..utils.parcel_finder_utils import *

from .sr4s.im.get_image_bands import request_date

def get_parcel_image(cadastral_reference: str, date: str, is_from_cadastral_reference: bool= True, parcel_geometry: str  = None, parcel_metadata: str = None, coordinates: list[float] = None, get_sr_image: bool = True) -> tuple:
    """
    Retrieves a SIGPAC image and data for a specific parcel.
    Arguments:
        cadastral_reference (str): The cadastral reference of the parcel to search for.
        date (str): The date for which the parcel data is requested, in 'DD-MM-YYYY' format.
        is_from_cadastral_reference (bool): If `True`, uses the cadastral reference to find the parcel; otherwise, uses the provided `parcel_geometry`.
        parcel_geometry (str): _Optional_; GeoJSON data of the parcel's polygon to use if `is_from_cadastral_reference` is `False`.
        parcel_metadata (str): _Optional_; User input metadata associated with the parcel to use if `is_from_cadastral_reference` is `False`.
        coordinates (list): _Optional_; Coordinates within parcel limits to find the parcel. Only used if `parcel_geometry` is `None` and if `is_from_cadastral_reference` is `False`.
        get_sr_image (bool): _Optional_; Get the Super-Resolved version of the parcel's image. Default is `True`.
    Returns:
        geometry (dict): GeoJSON geometry with the parcel's limits.
        metadata (dict): Metadata associated with the parcel.
        sigpac_image_url (str): URL of the SIGPAC image.
    """
    init = datetime.now()
    request_date.set(date)
    year, month, _ = date.split("-")
    # Get parcel data
    if cadastral_reference:
        geometry, metadata = find_from_cadastral_registry(cadastral_reference)
    elif not is_from_cadastral_reference:
        if not parcel_geometry and not coordinates:
            raise ValueError("GeoJSON data or parcel coordinates must be provided when not using cadastral reference.")
        elif parcel_geometry:
            # Retrieve geometry from map drawing geometry
            geometry = json.loads(parcel_geometry)
            # Generate metadata from user input
            metadata = json.loads(parcel_metadata)
        elif coordinates:
            # Retrieve geometry from coordinates
            lat, lng = coordinates
            cadastral_ref = generate_cadastral_ref_from_coords(lat, lng)
            geometry, metadata = find_from_cadastral_registry(cadastral_ref)
    else:
        raise ValueError("Cadastral reference missing. Reference must be provided when not using location or GeoJSON/coordinates")
    # Get GeoJSON data and dataframe and list of UTM zones
    # Open a file in write mode and save the string
    os.makedirs(SEN2SR_SR_DIR, exist_ok=True)
    with open(GEOJSON_FILEPATH, "w") as file:
        file.write(str(geometry).replace("'", '"').replace("(","[").replace(")","]"))  # format GeoJSON correctly
    geojson_data, gdf = get_geojson_data(geometry, metadata)
    zones_utm = get_tiles_polygons(gdf)
    list_zones_utm = list(zones_utm)

    # Get bands for RGB/SR processing
    bands = [b + f"_{RESOLUTION}m" for b in SR_BANDS]
    if not get_sr_image:
        # Remove B08 band
        bands.pop()
    
    sigpac_image_url = ''
    print("GET_SR_BENCHMARK", GET_SR_BENCHMARK)
    if GET_SR_BENCHMARK:
        reset_dir(BM_DATA_DIR)
        reset_dir(BM_RES_DIR)
        sigpac_image_url = download_parcel_image(cadastral_reference, geojson_data, list_zones_utm, year, month, bands)
    time1 = datetime.now()-init
    msg1 = f"\nTIME TAKEN (SENTINEL HUB / MINIO + SR4S): {time1}" if sigpac_image_url else ""
    init2 = datetime.now()
    sigpac_image_name = download_sen2sr_parcel_image(geometry, date)
    sigpac_image_url = f"{os.getenv('API_URL')}/uploads/{os.path.basename(sigpac_image_name)}?v={int(time.time())}"
    msg2 = f"\nTIME TAKEN (SEN2SR): {datetime.now()-init2}"
    msg3 = ''
    if GET_SR_BENCHMARK:
        init3 = datetime.now()
        compare_sr_metrics()
        msg3 = f"\nTIME TAKEN (BENCHMARK): {datetime.now()-init3}"

    print(msg1 + msg2 + msg3)

    return geometry, metadata, sigpac_image_url

def download_sen2sr_parcel_image(geometry, date):
    """
    Download and super-resolve parcel image cropped from Sentinel imagery cubo data.

    Arguments:
        geometry (dict): Geometry containing the parcel/image's limits.
        date (str): Most recent date to get the image from.
    
    Returns:
        sigpac_image_url (str): Path to display SR image.
    """
    min_size = 128
    if geometry:
        poly = shape(geometry)
        lon, lat = float(poly.centroid.x), float(poly.centroid.y)
        print("Centroid:", lat, lon)
    else:
        raise ValueError("Error: No GeoJSON or coordinates provided for parcel.")
    bands= BANDS

    sr_size=max(min_size, polygon_pixel_size(geometry))

    year, month, day = date.split("-")
    formatted_date = datetime(year=int(year), month=int(month), day=int(day))
    delta = 15
    end_date = formatted_date.strftime("%Y-%m-%d")
    start_date = (formatted_date - timedelta(days=delta)).strftime("%Y-%m-%d")

    sigpac_image_name = os.path.basename(get_sr_image(lat, lon, bands, start_date, end_date, sr_size))

    return sigpac_image_name

def download_parcel_image(cadastral_reference, geojson_data, list_zones_utm, year, month, bands):
    try:
        # Download image bands
        geometry =  geojson_data['features'][0]['geometry']
        rgb_images_path = download_tile_bands(list_zones_utm, year, month, bands, geometry)
        if not rgb_images_path or len(rgb_images_path) < len(bands):
            error_message = "No images are available for the selected date, images are processed at the end of each month."
            print(error_message)
            abort(404, description=error_message)

        __, png_paths, __ = get_rgb_parcel_image(cadastral_reference, geojson_data, rgb_images_path)
        
        sigpac_image_name = png_paths.pop()  # there should only be one file

        # Upload and fetch latest image
        sigpac_image_url = f"{os.getenv('API_URL')}/uploads/{os.path.basename(sigpac_image_name)}?v={int(time.time())}"
        return sigpac_image_url.split("?")[0]
    except Exception as e:
        traceback.print_exc()
        print(f"An error occurred (download_parcel_image): {str(e)}")
        raise

def get_rgb_parcel_image(cadastral_reference, geojson_data, rgb_images_path):
    """
    Processes a list of RGB images by cropping them to the geometries specified in the provided GeoJSON data,
    ensuring all images are in the same format, and then generates output files for further use.
    Args:
        cadastral_reference (str): The cadastral reference identifier for the parcel.
        geojson_data (dict): A GeoJSON-like dictionary containing features with geometries to crop images by.
        rgb_images_path (list of str): List of file paths to the RGB images to be processed.
    Returns:
        tuple:
            out_dir (str): The output directory where processed images are saved.\n
            png_paths (list of str): List of file paths to the generated PNG images.\n
            rgb_tif_paths (list of str): List of file paths to the generated RGB TIFF images.
    Raises:
        ValueError: If the input images are not all in the same file format.
    """
    try:
        unique_formats = list(
            set(
                f.split(".")[-1].lower()
                for f in rgb_images_path
                if isinstance(f, str) and "." in f
            )
        )
        if len(unique_formats) > 1:
            raise ValueError(
                f"Unsupported format. You must upload images in one unique format."
            )
        
        # Crop the parcel outline using the geomatry available
        cropped_parcel_masks_paths = []
        for feature in geojson_data["features"]:
            geometry = feature["geometry"]
            geometry_id = cadastral_reference
            cropped_parcel_masks_paths.extend(cut_from_geometry(geometry, unique_formats[0], rgb_images_path, geometry_id))

        out_dir, png_paths, rgb_tif_paths = get_rgb_composite(cropped_parcel_masks_paths, geojson_data)

        return out_dir, png_paths, rgb_tif_paths
    except Exception as e:
        print(f"An error occurred (get_rgb_parcel_image): {str(e)}")
        raise
