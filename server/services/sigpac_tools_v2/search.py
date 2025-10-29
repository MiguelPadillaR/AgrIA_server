import requests
import structlog

from ...utils.parcel_finder_utils import build_cadastral_reference
from ._globals import BASE_URL, QUERY_URL
from .utils import find_community, get_parcel_metadata_and_geometry, read_cadastral_registry

logger = structlog.get_logger()


def search(data: dict) -> dict:
    """Search for a specific location in the SIGPAC database

    Search for the information of the given location in the SIGPAC database. The search can be done by specifying the community, province, municipality, polygon and parcel.

    Parameters
    ----------
    data : dict
        Dictionary with the data of the location to search. It must be a dictionary with the following keys: [ community, province, municipality, polygon, parcel ]

    Returns
    -------
    dict
        Dictionary with information about the location searched and the coordinates of the polygon or parcels

    Raises
    ------
    ValueError
        If the community is not specified and it is required to search for the location
    """
    comm = data.get("community", None)
    provi = data.get("province", None)
    muni = data.get("municipality", None)
    polg = data.get("polygon", None)
    parc = data.get("parcel", None)


    if not comm:
        if not provi:
            raise ValueError(
                '"Community" has not been specified, neither has been "province" and it is compulsory to find the community associated'
            )
        else:
            comm = find_community(provi)

    if comm and provi and muni and polg and parc:
        logger.info("Searching for specified parcel.")
        base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfoparc/{provi}/{muni}/0/0/{polg}/{parc}.geojson"
        geometry, metadata = get_parcel_metadata_and_geometry(base_endpoint)
        return geometry, metadata
    else:
        raise ValueError(
            '"Community" has not been specified and it could have not been found from the "province" parameter'
        )
