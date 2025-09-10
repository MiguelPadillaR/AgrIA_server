import json
import time
from flask import abort
from sigpac_tools.find import find_from_cadastral_registry, geometry_from_coords
from ..utils.parcel_finder_utils import *
import os

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
    year, month, _ = date.split("-")

    # Get parcel data
    if cadastral_reference:
        geometry, metadata = find_from_cadastral_registry(cadastral_reference)
    elif not is_from_cadastral_reference:
        # Generate metadata from user input
        metadata = json.loads(parcel_metadata)

        if not parcel_geometry and not coordinates:
            raise ValueError("GeoJSON data or parcel coordinates must be provided when not using cadastral reference.")
        elif parcel_geometry:
            # Retrieve geometry from map drawing geometry
            geometry = json.loads(parcel_geometry)
            
        else:
            # Retrieve geometry from coordinates
            lat, lng = coordinates    
            feature_collection = geometry_from_coords("parcela", lat, lng, 0)
            if feature_collection['type'] == "FeatureCollection" and len(feature_collection['features']) > 1:
                # Find parcel associated to coordinates
                feature = find_nearest_feature_to_point(feature_collection, coordinates[0], coordinates[1])
                if feature:
                    geometry = feature["geometry"]
                else:
                    # Use all parcels found as parcel image
                    geometry = merge_and_convert_to_geometry(feature_collection) 
            else:
                # Only one parcel found
                geometry = feature_collection
    else:
        raise ValueError("Cadastral reference missing. Reference must be provided when not using location or GeoJSON/coordinates")

    # Get GeoJSON data and dataframe and list of UTM zones
    geojson_data, gdf = get_geojson_data(geometry, metadata)
    zones_utm = get_tiles_polygons(gdf)
    list_zones_utm = list(zones_utm)

    # if get_sr_image:
    #     # Download SR RGB image:
    #     sigpac_image_url = None    
    # else:
    # Download normal RGB image:
    sigpac_image_url = download_normal_rgb_image(cadastral_reference, geojson_data, list_zones_utm, year, month)

    return geometry, metadata, sigpac_image_url

def download_normal_rgb_image(cadastral_reference, geojson_data, list_zones_utm, year, month):
    # Download RGB image:
    rgb_images_path = download_tiles_rgb_bands(list_zones_utm, year, month)
    if not rgb_images_path:
        error_message = "No images are available for the selected date, images are processed at the end of each month."
        print(error_message)
        abort(404, description=error_message)
        
    out_dir, png_paths, rgb_tif_paths = get_rgb_parcel_image(cadastral_reference, geojson_data, rgb_images_path)

    sigpac_image_name = png_paths.pop()  # there should only be one file

    # Upload and fetch latest image
    sigpac_image_url = f"{os.getenv('API_URL')}/uploads/{os.path.basename(sigpac_image_name)}?v={int(time.time())}"
    return sigpac_image_url.split("?")[0]

def get_rgb_parcel_image(cadastral_reference, geojson_data, rgb_images_path_values):
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
    unique_formats = list(
        set(
            f.split(".")[-1].lower()
            for f in rgb_images_path_values
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
        cropped_parcel_masks_paths.extend(cut_from_geometry(geometry, unique_formats[0], rgb_images_path_values, geometry_id))
    
    unique_masks = set(cropped_parcel_masks_paths)

    out_dir, png_paths, rgb_tif_paths = rgb(unique_masks)

    return out_dir, png_paths, rgb_tif_paths
