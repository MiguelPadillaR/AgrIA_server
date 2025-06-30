from sigpac_tools.find import find_from_cadastral_registry
from ..utils.parcel_finder_utils1 import *
import os

def get_parcel_image( cadastral_reference: str, date: str) -> tuple:
    """
    Retrieves a SIGPAC image and data for a specific parcel.
    date (str): The date for which the parcel data is requested, in 'DD-MM-YYYY' format.
    Arguments:
        cadastral_reference (str): The cadastral reference of the parcel to search for.
    Returns:
        geometry (dict): GeoJSON geometry with the parcel's limits.
        metadata (dict): Metadata associated with the parcel.
        sigpac_image_url (str): URL of the SIGPAC image.
    """
    year = date.split("-")[-1]
    month = date.split("-")[-2]
    
    # Get parcel data
    geometry, metadata = find_from_cadastral_registry(cadastral_reference)
    
    # Get GeoJSON data and dataframe and list of UTM zones
    geojson_data, gdf = get_geojson_data(geometry, metadata)
    zones_utm = get_tiles_polygons(gdf)
    list_zones_utm = list(zones_utm)

    # Download RGB image:
    rgb_images_path = download_tiles_rgb_bands(list_zones_utm, year, month)
    
    # TODO: Keep refactoring
    
    if not rgb_images_path:
        print("No images are available for the selected date, images are processed at the end of each month.")
        return None, None

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
    cropped_images = []
    for feature in geojson_data["features"]:
        geometry = feature["geometry"]
        geometry_id = cadastral_reference
        cropped_images.extend(cut_from_geometry(geometry, unique_formats[0], rgb_images_path, geometry_id))


    #TODO: Get image from geometry (image-workflow.pptx)
    sigpac_image_name = ''

    sigpac_image_url = f"{os.getenv('API_URL')}/uploads/{sigpac_image_name}"

    return geometry, metadata, sigpac_image_url

