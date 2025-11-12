import io
import math
import numpy as np
import random
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from sentinelhub import BBox, CRS
from ..constants import LAT_MIN, LAT_MAX, LON_MIN, LON_MAX

def get_bbox_from_zoom(lat, lon, size, zoom):
    """
    Compute a bounding box in WGS84 matching Google Maps' zoom level.
    
    lat, lon: center coordinates
    size: (width_px, height_px)
    zoom: Maps' zoom level
    """
    # meters per pixel at this latitude and zoom
    mpp = 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)
    
    # total size in meters
    width_m = size[0] * mpp
    height_m = size[1] * mpp
    
    # convert meters to degrees (approx)
    meters_per_degree_lat = 111320.0
    meters_per_degree_lon = 111320.0 * math.cos(math.radians(lat))
    
    width_deg = width_m / meters_per_degree_lon
    height_deg = height_m / meters_per_degree_lat
    
    min_lon = lon - width_deg / 2
    max_lon = lon + width_deg / 2
    min_lat = lat - height_deg / 2
    max_lat = lat + height_deg / 2
    
    return BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)

def get_zoom_from_bbox(bbox: BBox, size: tuple):
    """
    Given a SentinelHub bbox + image size, compute the Google Maps zoom level
    and the equivalent Google bbox that matches coverage.
    
    bbox: BBox in WGS84
    size: (width_px, height_px)
    
    Returns: (zoom, google_bbox)
    """
    # Extract bbox coordinates
    min_lon, min_lat, max_lon, max_lat = bbox
    width_deg = max_lon - min_lon
    height_deg = max_lat - min_lat
    lat_center = (min_lat + max_lat) / 2
    
    # Approx conversion: degrees → meters
    meters_per_degree_lat = 111320.0
    meters_per_degree_lon = 111320.0 * math.cos(math.radians(lat_center))
    
    width_m = width_deg * meters_per_degree_lon
    height_m = height_deg * meters_per_degree_lat
    
    # Sentinel resolution (meters per pixel)
    mpp_x = width_m / size[0]
    mpp_y = height_m / size[1]
    mpp = (mpp_x + mpp_y) / 2   # average
    
    # Compute Google zoom
    zoom_float = math.log2((156543.03392 * math.cos(math.radians(lat_center))) / mpp)
    zoom = max(0, min(21, round(zoom_float)))  # clamp to [0,21]
        
    return zoom #, google_bbox

def get_bbox_from_center(lat, lon, width_px, height_px, resolution_m):
    """
    Compute a bounding box around a center coordinate that will produce
    an image of (width_px, height_px) pixels at a specified resolution (meters per pixel).

    Args:
        lat, lon (float): Center coordinates.
        width_px, height_px (int): Desired image size in pixels.
        resolution_m (float): Desired resolution in meters per pixel.

    Returns:
        BBox: Bounding box in WGS84 suitable for SentinelHub requests.
    """
    # Physical size of image in meters
    MAX_PX_SIZE = 1500
    width_m = min(MAX_PX_SIZE, width_px * resolution_m)
    height_m = min(MAX_PX_SIZE, height_px * resolution_m)

    # Convert meters to degrees (approximate, valid near the given latitude)
    METERS_PER_DEGREE_LAT = 111320.0
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))

    width_deg = width_m / meters_per_degree_lon
    height_deg = height_m / METERS_PER_DEGREE_LAT

    min_lon = lon - width_deg / 2
    max_lon = lon + width_deg / 2
    min_lat = lat - height_deg / 2
    max_lat = lat + height_deg / 2

    return BBox(bbox=[min_lon, min_lat, max_lon, max_lat], crs=CRS.WGS84)

def get_n_random_coordinate_pairs(amount:int, bounded_zone = [LAT_MIN, LAT_MAX, LON_MIN, LON_MAX]):
    """
    Generate random coordinates from a bounded zone.
    
    amount: number of coordinate pairs to generate
    
    Returns: list of (lat, lon) tuples
    """    
    coordinates = []
    lat_min, lat_max, lon_min, lon_max = bounded_zone
    for _ in range(amount):
        lat = random.uniform(lat_min, lat_max)
        lon = random.uniform(lon_min, lon_max)
        coordinates.append((lat, lon))
    
    return coordinates

def generate_evalscript(
    bands=["B04", "B03", "B02"],
    units="REFLECTANCE",
    data_type=None,
    mosaicking_type="SIMPLE",
    bit_scale="UINT8",
    id=None,
    rendering=None,
    mask=None,
    resampling=None,
    clip_range=(0.0, 0.3),
    gamma=1.0,
):
    """
    Generate an evalscript for SentinelHub requests. The script is dinamically generated with the values provided.

    DOC: https://docs.sentinel-hub.com/api/latest/evalscript/v3/
    
    Arguments:
        bands (list | None): Bands to include, e.g. `"B02"` or `["B02", "B03", "B04"]`.
        units (str | None): Units of the input bands (e.g. `"DN"`, `"REFLECTANCE"`). If None, omitted.
        data_type (str | None): Data type for input bands. If None, omitted.
        mosaicking_type (str | None): Type of mosaicking. If None, omitted.
        bit_scale (str | None): Bit scale of output bands. If None, `"AUTO"`.
        id (str): Response ID. If None, omitted.
        rendering (bool): Whether to apply rendering/visualization. If None, omitted.
        mask (bool): Whether to output mask. If None, omitted.
        resampling (str):
        clip_range (tuple):
        gamma (float):

    Returns:
        evalscript (str): The generated evalscript for SentinelHub image request.
    """
    bands_str = ", ".join([f'"{band}"' for band in bands])

    input_opts = [f"bands: [{bands_str}]"]
    if units:
        input_opts.append(f'units: "{units}"')
    if data_type:
        input_opts.append(f'dataType: "{data_type}"')
    if mosaicking_type:
        input_opts.append(f'mosaicking: "{mosaicking_type}"')

    output_opts = [f"bands: {len(bands)}"]
    if id:
        output_opts.append(f'id: "{id}"')
    if bit_scale:
        output_opts.append(f'sampleType: "{bit_scale}"')
    if rendering is not None:
        output_opts.append(f"rendering: {str(rendering).lower()}")
    if mask is not None:
        output_opts.append(f"mask: {str(mask).lower()}")
    if resampling:
        output_opts.append(f'resampling: "{resampling}"')

    input_str = ",\n\t\t".join(input_opts)
    output_str = ",\n\t\t".join(output_opts)

    minv, maxv = clip_range
    stretch = f"(val - {minv}) / ({maxv - minv})"
    stretch = f"Math.max(0, Math.min(1, {stretch}))"
    if gamma != 1.0:
        stretch = f"Math.pow({stretch}, 1.0/{gamma})"

    # multiply by 255 if UINT8
    mult = " * 255" if bit_scale == "UINT8" else ""

    # apply stretch for each band
    out_expr = ", ".join([f"{stretch.replace('val', f'sample.{b}')}{mult}" for b in bands])

    return f"""
//VERSION=3
function setup() {{
  return {{
    input: [{{
      {input_str}
    }}],
    output: {{
      {output_str}
    }}
  }};
}}

function evaluatePixel(sample) {{
  return [{out_expr}];
}}
"""

def save_tiff(image: np.ndarray, filename: str, bbox, crs="EPSG:4326"):
    """
    Save a numpy array as a GeoTIFF with georeferencing info.
    
    Args:
        image (np.ndarray): Image array (H, W) or (H, W, C).
        filename (str): Output file path (.tiff).
        bbox (sentinelhub.BBox): Bounding box used in the request.
        crs (str): Coordinate reference system (default WGS84).
    """
    height, width = image.shape[:2]
    count = 1 if image.ndim == 2 else image.shape[2]

    # Create an affine transform (maps pixel <-> geo coordinates)
    transform = from_bounds(*bbox, width=width, height=height)

    with rasterio.open(
        filename,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=count,
        dtype=image.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        if count == 1:
            dst.write(image, 1)
        else:
            for i in range(count):
                dst.write(image[:, :, i], i + 1)

def perform_image_sanity_check(lat, lon, image_bytes):
    """
    Perform a sanity check over the response's image
    Arguments:
        image_bytes (bytes): Sentinel Hub request image in bytes format.
        lat (float): Latitude.
        lon (float): Longitude.
    Return:
        has_imagery (bool): If True, there is a valid image in the response.
    """
    has_imagery = True
    
    # # Quick sanity check: if file is too small, probably "no imagery"
    # if len(image_bytes) < 15_000:  # tweak threshold as needed
    #     print(f"No imagery (small file) at {lat},{lon}")
    #     return False

    # Check if the image is mainly white (no imagery available)
    iamge_converted = Image.open(io.BytesIO(image_bytes)).convert("L")
    arr = np.array(iamge_converted)
    std_val = np.std(arr)

    # If almost all pixels are very bright (white background) and there's little variation, it's probably "no imagery"
    if np.mean(arr) > 230 and std_val < 15:
        print(f"No imagery available for {lat},{lon}")
        has_imagery = False
    
    return has_imagery
