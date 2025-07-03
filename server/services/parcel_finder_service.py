import time
from sigpac_tools.find import find_from_cadastral_registry
from ..utils.parcel_finder_utils import *
import os

def get_parcel_image( cadastral_reference: str, date: str) -> tuple:
    """
    Retrieves a SIGPAC image and data for a specific parcel.
    Arguments:
        cadastral_reference (str): The cadastral reference of the parcel to search for.
        date (str): The date for which the parcel data is requested, in 'DD-MM-YYYY' format.
    Returns:
        geometry (dict): GeoJSON geometry with the parcel's limits.
        metadata (dict): Metadata associated with the parcel.
        sigpac_image_url (str): URL of the SIGPAC image.
    """
    year = date.split("-")[0]
    month = date.split("-")[1]
    
    # Get parcel data
    geometry, metadata = find_from_cadastral_registry(cadastral_reference)
    
    # Get GeoJSON data and dataframe and list of UTM zones
    geojson_data, gdf = get_geojson_data(geometry, metadata)
    zones_utm = get_tiles_polygons(gdf)
    list_zones_utm = list(zones_utm)

    # Download RGB image:
    rgb_images_path = download_tiles_rgb_bands(list_zones_utm, year, month)
    
    if not rgb_images_path:
        print("No images are available for the selected date, images are processed at the end of each month.")
        return None, None

    out_dir, png_paths, rgb_tif_paths = get_rgb_parcel_image(cadastral_reference, geojson_data, rgb_images_path)

    #TODO: Get image from geometry (image-workflow.pptx)
    
    sigpac_image_name = png_paths.pop()  # there should only be one file

    # Upload and fetch latest image
    sigpac_image_url = f"{os.getenv('API_URL')}/uploads/{os.path.basename(sigpac_image_name)}?v={int(time.time())}"

    return geometry, metadata, sigpac_image_url.split("?")[0]

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
            out_dir (str): The output directory where processed images are saved.
            png_paths (list of str): List of file paths to the generated PNG images.
            rgb_tif_paths (list of str): List of file paths to the generated RGB TIFF images.
    Raises:
        ValueError: If the input images are not all in the same file format.
    Note:
        This function relies on external functions `cut_from_geometry` and `rgb` to perform cropping and image processing.
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

