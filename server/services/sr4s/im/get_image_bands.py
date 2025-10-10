import time
import numpy as np

from datetime import datetime, timedelta

from sentinelhub import SHConfig, DataCollection, MimeType, SentinelHubRequest, bbox_to_dimensions
from .sh_config import CONFIG_NAME
from .utils import *
from ....config.constants import BANDS_DIR
from ..constants import DELTA_DAYS, RESOLUTION, SIZE

from contextvars import ContextVar

request_date: ContextVar[str] = ContextVar("request_date", default="")

config = SHConfig(CONFIG_NAME)

if not config.sh_client_id or not config.sh_client_secret:
    print("Warning! To use Process API, please provide the credentials (OAuth client ID and client secret).")

def download_from_sentinel_hub(lat, lon, filename):
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
    date_info, band_ext = filename.split("-")
    year, month = date_info.split("_")
    # Get a range of dates to ensure cloud-free scenes
    date = datetime(year=int(year), month=int(month), day=int(request_date.get().split("-")[-1]))
    date = date if date < datetime.now() else datetime.now() - timedelta(days=1)
    delta = DELTA_DAYS
    initial_date = str((date - timedelta(days=delta)).isoformat())
    final_date = str(date.isoformat())

    # Retieve imagen band and save it
    image = get_cloudless_image(evalscript, bbox, width, height, config, initial_date, final_date)
    filepath = BANDS_DIR / filename
    save_tiff(image, filepath, bbox, crs="EPSG:4326")

    print(f"Sentinel band image saved to {filepath}")


def get_cloudless_image(evalscript, bbox, width, height, config, initial_date, final_date, days_back=15, max_tries=5, maxcc=0.2, relax_clouds=True):
    """
    Retrieve Sentinel-2 imagery with adaptive backtracking and empty-image checks.
    """
    attempt = 0
    current_initial = datetime.fromisoformat(initial_date)
    current_final = datetime.fromisoformat(final_date)
    current_maxcc = maxcc

    while attempt < max_tries:
        print(
            f"🛰️ Attempt {attempt+1}: Searching between {current_initial.date()} → {current_final.date()} (maxcc={current_maxcc:.2f})"
        )

        try:
            sh_request = SentinelHubRequest(
                evalscript=evalscript,
                input_data=[
                    SentinelHubRequest.input_data(
                        DataCollection.SENTINEL2_L2A.define_from("s2l2a", service_url=config.sh_base_url),
                        time_interval=(current_initial.date().isoformat(), current_final.date().isoformat()),
                        maxcc=current_maxcc,
                    )
                ],
                responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
                bbox=bbox,
                size=(width, height),
                config=config,
            )

            data = sh_request.get_data()
            if not data or len(data[0].shape) < 2:
                raise ValueError("Empty response (no imagery returned).")

            img = data[0]
            if np.all((img == 0) | np.isnan(img)):
                raise ValueError("Received empty image (all zeros or NaNs).")

            print(f"✅ Found valid imagery on attempt {attempt+1}")
            return img

        except ValueError as e:
            print(f"⚠️  Attempt {attempt+1} failed: {e}")

        # Push search window backward
        current_final = current_initial - timedelta(days=1)
        current_initial = current_final - timedelta(days=days_back)

        # Optionally relax cloud constraint after a few attempts
        if relax_clouds and attempt >= 2:
            current_maxcc = min(1.0, current_maxcc + 0.1)

        attempt += 1

    raise RuntimeError("❌ No valid Sentinel-2 image found after all attempts.")

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
