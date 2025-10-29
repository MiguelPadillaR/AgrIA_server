import requests
import structlog

from ._globals import BASE_URL, QUERY_URL
from .utils import find_community, get_parcel_data_and_geometry

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
    prov = data.get("province", None)
    muni = data.get("municipality", None)
    polg = data.get("polygon", None)
    parc = data.get("parcel", None)
    id = data.get("id_inm", None)

    crs = data.get("crs", None)
    lat = data.get("lat", None)
    lon = data.get("lon", None)

    if not comm:
        if not prov:
            raise ValueError(
                '"Community" has not been specified, neither has been "province" and it is compulsory to find the community associated'
            )
        else:
            comm = find_community(prov)

    if crs and lat and lon:
        logger.info(f"Searching for specified parcel in coords: {lat}, {lon} .")
        base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfobypoint/{crs}/{lat}{lon}"
        response = get_parcel_data_and_geometry(base_endpoint)
        return response
    elif comm:
        if prov:
            if muni:
                if polg:
                    if parc:
                        # if id:
                        #     logger.info("Searching for the specified enclosure.")
                        #     base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfo/{prov}/{muni}/0/0/{polg}/{parc}"
                        #     response = get_parcel_data_and_geometry(base_endpoint)
                        #     return response
                        # else:    
                        #     logger.info("Searching for all parcels for cadastral code.")
                        #     base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfoparc/{prov}/{muni}/0/0/{polg}/{parc}"
                        #     response = get_parcel_data_and_geometry(base_endpoint)
                        #     return response
                        logger.info("Searching for specified parcel.")
                        base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfoparc/{prov}/{muni}/0/0/{polg}/{parc}"
                        response = get_parcel_data_and_geometry(base_endpoint)
                        return response
                    else:
                        logger.info(f"Searching for the parcels of the polygon {polg}")
                        base_endpoint = f"{BASE_URL}/{QUERY_URL}/refcatparcela/{prov}/{muni}/0/0/{polg}/{parc}"
                        response = get_parcel_data_and_geometry(base_endpoint)
                        return response
                else:
                    logger.info(
                        f"Searching for the polygons of the municipality {muni}"
                    )
                    base_endpoint = f"{BASE_URL}/{QUERY_URL}/recinfoparc/{prov}/{muni}/0/0/{polg}/{parc}"
                    response = get_parcel_data_and_geometry(base_endpoint)
                    return response
            else:
                logger.info(f"Searching for the municipalities of the province {prov}")
                base_endpoint = f"{BASE_URL}/codigossigpac/municipio{prov}.json"
                response = requests.get(base_endpoint)
                json = response.json()
                return json
        else:
            logger.info(f"Searching for the provinces of Spain")
            base_endpoint = f"{BASE_URL}/codigossigpac/provincia.json"
            response = requests.get(base_endpoint)
            json = response.json()
            return json

    else:
        raise ValueError(
            '"Community" has not been specified and it could have not been found from the "province" parameter'
        )
