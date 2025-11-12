import requests
import structlog

from ...utils.parcel_finder_utils import build_cadastral_reference

from ._globals import BASE_URL,QUERY_URL

logger = structlog.get_logger()


def generate_cadastral_ref_from_coords(lat: float, lon: float, crs: str = "4258") -> str:
    """Gets the cadastral reference of the given coordinates and reference in the given parcel.
    WARNING: The result is synthetic and does not necesarilly match a real SIGPAC cadastral reference.
    However, it works for the system's scope.

    Parameters
    ----------
    lat : float
        Latitude of the location
    lon : float
        Longitude of the location
    crs : str
        Coordinates reference system

    Returns
    -------
    str
        Cadastral code of the found reference

    Raises
    ------
        ValueError: If JSON is invalid
    """
    # Search enclosure by coords
    logger.info(f"Retrieving info from parcel at coordinates: {lat}, {lon}")
    base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfobypoint/{crs}/{lon}/{lat}.json"
    logger.debug(f"SIGPAC request URL: {base_endpoint}")
    response = requests.get(base_endpoint)

    try:
        response = response.json()[0]
    except Exception as e:
        logger.exception(f"Failed to parse SIGPAC JSON response: {e}")
        raise ValueError("Invalid JSON returned by SIGPAC")

    # Get cadastral data from responses
    provi = str(response["provincia"]).zfill(2) + "-"
    munic = str(response["municipio"]).zfill(3) + "-"
    polig = str(response["poligono"]).zfill(3)
    parcel = str(response["parcela"]).zfill(5)

    # Build cadastral reference
    cadastral_ref = build_cadastral_reference(provi, munic, polig, parcel)
    logger.info(f'Associated synthetic cadastral reference: {cadastral_ref}')
    
    # geometry, _ = search(read_cadastral_registry(cadastral_ref))

    return cadastral_ref