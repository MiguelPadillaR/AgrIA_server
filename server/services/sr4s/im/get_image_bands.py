import time
from datetime import datetime, timedelta

from sentinelhub import SHConfig, DataCollection, MimeType, SentinelHubRequest, bbox_to_dimensions
from .sh_config import CONFIG_NAME
from .utils import *
from ....config.constants import BANDS_DIR
from ..constants import DELTA_DAYS, RESOLUTION, SIZE

config = SHConfig(CONFIG_NAME)

if not config.sh_client_id or not config.sh_client_secret:
    print("Warning! To use Process API, please provide the credentials (OAuth client ID and client secret).")

# ----------------------------
# SENTINEL REQUEST
# ----------------------------
def download_sentinel_image(lat, lon, size, filename, evalscript):
    """
    Fetches a Sentinel image for the given lat, lon, size, and zoom level,
    and saves it to the specified filename.
    
    Arguments:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.
        size (tuple): Size of the image in pixels (width, height).
        zoom (int): Zoom level for the image.
        filename (str): Filename to save the image.
        evalscript (str): Javascript code that defines how the satellite data shall be retrieved and processed.
    """
    bbox = get_bbox_from_center(lat, lon, size[0], size[-1], RESOLUTION)
    width, height = bbox_to_dimensions(bbox, resolution=RESOLUTION)
    year, month = filename.split("-")[0].split("_")
    # Get a range of dates to ensure cloud-free scenes
    date = datetime(year=int(year), month=int(month), day=random.randint(1,28))
    date = date if date < datetime.now() else datetime.now() - timedelta(days=1)
    delta = DELTA_DAYS
    look_from = date - timedelta(days=delta)
    initial_date = f"{look_from.year}-{look_from.month:02d}-{look_from.day:02d}"
    final_date = f"{date.year}-{date.month}-{date.day:02d}"

    sh_request = SentinelHubRequest(
        evalscript=evalscript,
        input_data=[
            SentinelHubRequest.input_data(
                DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url),
                time_interval=(initial_date, final_date),
                maxcc=0.2  # maximum cloud coverage (20%)
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=(width, height),
        config=config,
    )
    # Retieve imagen band and save it
    image = sh_request.get_data()[0]
    filepath = BANDS_DIR / filename
    save_tiff(image, filepath, bbox, crs="EPSG:4326")

    print(f"Sentinel band image saved to {filepath}")

def download_image_bands(lat, lon, size, filename=None, bands=["B02", "B03", "B04"]):
    """
    Downloads separate Sentinel image bandsfor the given latitude and longitude.
    
    Arguments:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.
        size (tuple): Size of the image in pixels (width, height).
        filename (str): Filename to save the image.
        bands (list): List of bands to download (e.g., ["B02", "B03", "B04"]).
    Returns:
        band_files_list (list): List of band file paths.
    """
    band_files_list = []
    for band in bands:
        file_path = filename + f"-{band}_{RESOLUTION}m.tif" if filename is not None else f"{str(lat)[:8]}_{str(lon)[:8]}-{band}_{RESOLUTION}m.tif"
        print(f"Fetching images for coordinates: {lat}, {lon}")
        
        # Get script that will retrieve  image bands
        evalscript_band = generate_evalscript(
            bands=[band],
        )

        download_sentinel_image(lat, lon, size, file_path, evalscript_band)
        print()
        band_files_list.append(str(BANDS_DIR / file_path))

    return band_files_list

def download_sentinel_bands(lat, lon, filename):
    """
    Downloads Sentinel band image _.tif_ files, specifically, B02, B03, B04 and B08.
    Arguments:
        lat (float): Latitude.
        lon (float): Longitude.
        filename (str): Base filename to save the images.
    Returns:
        band_files_list (list): List of band file paths.
    """
    start_time = time.time()
    BANDS_DIR.mkdir(parents=True, exist_ok=True)
    bands=['B02', 'B03', 'B04', 'B08']
    size = (SIZE,SIZE)
    band_files_list = download_image_bands(lat, lon, size, filename, bands)
    print(f"\nTotal time:\t{(time.time() - start_time)/60:.1f} minutes")
    return band_files_list
    