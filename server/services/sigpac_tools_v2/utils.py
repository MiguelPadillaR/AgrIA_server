import requests
import structlog

from collections import defaultdict

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

from ._globals import PROVINCES_BY_COMMUNITY

logger = structlog.get_logger()


def find_community(province_id: int) -> int:
    """Finds the community of the given province id

    Parameters
    ----------
    province_id : int
        Province id to search for

    Returns
    -------
    int
        Returns the community id of the given province id
    """
    for comunidad, provincias in PROVINCES_BY_COMMUNITY.items():
        if province_id in provincias:
            return comunidad
    return None

def read_cadastral_registry(registry: str) -> dict:
    """Read the cadastral reference, validates it and return its data as a dictionary.
    The expected format is:
        - 2 characters for the province
        - 3 characters for the municipality
        - 1 character for the section
        - 3 characters for the polygon
        - 5 characters for the parcel
        - 4 characters for the id
        - 2 characters for the control

    20 characters in total.

    Parameters
    ----------
        registry (str): Cadastrial reference to read

    Returns
    -------
        dict: Data extracted from the cadastral reference

    Raises
    -------
        ValueError: If the length of the cadastral reference is not 20 characters
    """
    registry = registry.upper().replace(" ", "")
    if len(registry) != 20:
        raise ValueError("The cadastral reference must have a length of 20 characters")

    reg_prov = registry[:2]
    reg_mun = registry[2:5]
    reg_sec = registry[5]
    reg_pol = registry[6:9]
    reg_par = registry[9:14]
    reg_id = registry[14:18]
    reg_control = registry[18:]

    # Will raise an error if the reference is not valid or if it is urban, in any other case, it will log the result and continue
    validate_cadastral_registry(registry)

    if not find_community(int(reg_prov)):
        raise ValueError(
            "The province of the cadastral reference is not valid. Please check if it is a correct rural reference and try again."
        )

    return {
        "province": int(reg_prov),
        "municipality": int(reg_mun),
        "section": reg_sec,
        "polygon": int(reg_pol),
        "parcel": int(reg_par),
        "id_inm": int(reg_id),
        "control": reg_control,
    }

def get_parcel_metadata_and_geometry(base_endpoint: str) -> dict:
    """Extract parcel metadata and geometry and returns them in a single JSON.
    
    Parameters
    ----------
        base_endpoint (str): Base SIGPAC endpoint

    Returns
    -------
        merged_json (dict): JSON with parcel metadata and geometry.

    Raises
    -------
        ValueError: If the reference is not valid
        NotImplementedError: If the reference is urban
    """
    logger.debug(f"Base endpoint:\t{base_endpoint}")
    response = requests.get(base_endpoint)
    response.raise_for_status()
    full_json = response.json()

    geometry = get_geometry(full_json)
    metadata = get_metadata(full_json)

    return geometry, metadata

def get_geometry(full_json: dict)-> dict:
    """ Extract parcel geometry info from all of the indificual encolusres info JSON file.
    
    Parameters:
    ----------
        full_json (dict): All parcel's enclousure info JSON data
        
    Returns:
    -------
        full_parcel_geometry (dict): GeoJSON for overall parcel geometry

    Raises
    -------
        ValueError: If no geometries were found
    """
    # Extract all geometries from features
    all_geometries = [shape(feature["geometry"]) for feature in full_json["features"]]

    if not all_geometries:
        raise ValueError("No geometries found in the provided JSON data.")

    logger.info("Found full metadata and geometry info for parcel.")

    # Merge all geometries into one (union of polygons)
    merged_geometry = unary_union(all_geometries)

    # Convert back to GeoJSON format
    full_parcel_geometry = mapping(merged_geometry)

    # Add CRS
    crs = f'{str(full_json["crs"]["type"]).lower()}:{full_json["crs"]["properties"]["code"]}'
    full_parcel_geometry['CRS'] = crs
    logger.info("Extracted geometry successfully.")

    return full_parcel_geometry

def get_metadata(full_json: dict)-> dict:
    """Extract parcel metadata and geometry and returns them in a single JSON.
    
    Parameters:
    ----------
        full_json (dict): All parcel's enclousure info JSON data
        
    Returns:
    -------
        full_parcel_metadata (dict): JSON metadata for the overall parcel

    Raises
    -------
        ValueError: If no data was found

    """

    # Prepare outputs
    query = []
    land_use = []
    total_surface = 0.0

    for feature in full_json.get("features", []):
        properties = feature.get("properties", {})
        
        # Extract and enrich info
        dn_surface = properties.get("superficie")
        uso_sigpac = properties.get("uso_sigpac")
        superficie_admisible = dn_surface
        inctexto = referencia_cat = None

        # Query info
        query_cols = ["admisibilidad", "altitud", "coef_regadio", "incidencias", 
                      "pendiente_media", "recinto", "region", "uso_sigpac"]
        query_entry = {col: properties.get(col) for col in query_cols}
        query_entry.update({
            "dn_surface": superficie_admisible,
            "inctexto": inctexto,
            "superficie_admisible": superficie_admisible,
            "uso_sigpac" : uso_sigpac
        })

        # Land use info
        land_use_entry = {
            "dn_superficie": dn_surface,
            "superficie_admisible": dn_surface,
            "uso_sigpac": properties.get("uso_sigpac")
        }

        # Append to lists
        query.append(query_entry)
        land_use.append(land_use_entry)

        # Add surface to total parcel surface
        total_surface += dn_surface

    # Parcel info
    parcel_info_cols = ["provincia", "municipio", "agregado", "poligono", "parcela"]
    parcel_info_entry = {col: properties.get(col) for col in parcel_info_cols}
    parcel_info_entry.update({
        "referencia_cat": referencia_cat,
        "dn_surface": total_surface
    })

    # --- GROUP LAND USES ---
    land_use_summary = defaultdict(float)
    for entry in land_use:
        uso = entry.get("uso_sigpac")
        if uso:
            land_use_summary[uso] += float(entry.get("dn_superficie", 0.0))

    # Convert back to list of dicts for output
    land_use_grouped = [
        {"uso_sigpac": uso, "dn_superficie": round(area, 4), "superficie_admisible": round(area, 4)}
        for uso, area in land_use_summary.items()
    ]

    # Build final parcel metadata
    full_parcel_metadata = {
        "arboles": None,
        "convergencia": None,
        "id": None,
        "isRecin": None,
        "parcelaInfo": parcel_info_entry,
        "query": query,
        "usos": land_use_grouped,
        "vigencia": None,
        "vuelo": None
    }
    logger.info("Extracted metadata successfully.")

    return full_parcel_metadata

def validate_cadastral_registry(reference: str) -> None:
    """Validate the cadastral reference

    Given a cadastral reference, it validates if the reference is correct or not by comparing the present control characters with the calculated expected ones.

    Based on the code proposed by Emil in the comments of http://el-divagante.blogspot.com/2006/11/algoritmos-y-dgitos-de-control.html

    Parameters
    ----------
        reference (str): Cadastral reference to validate

    Returns
    -------
        None

    Raises
    -------
        ValueError: If the reference is not valid
        NotImplementedError: If the reference is urban
    """

    sum_pd1 = 0
    sum_sd2 = 0
    mixt1 = 0
    reference = reference.upper().replace(" ", "")
    pos = [13, 15, 12, 5, 4, 17, 9, 21, 3, 7, 1]
    res = "MQWERTYUIOPASDFGHJKLBZX"

    if len(reference) != 20:
        raise ValueError("The cadastral reference must have a length of 20 characters")
    else:
        separated_ref = list(reference)

        for i in range(7):
            if separated_ref[i].isdigit():
                sum_pd1 += pos[i] * (ord(separated_ref[i]) - 48)
            else:
                if ord(separated_ref[i]) > 78:
                    sum_pd1 += pos[i] * (ord(separated_ref[i]) - 63)
                else:
                    sum_pd1 += pos[i] * (ord(separated_ref[i]) - 64)

        for i in range(7):
            if separated_ref[i + 7].isdigit():
                sum_sd2 += pos[i] * (ord(separated_ref[i + 7]) - 48)
            else:
                if ord(separated_ref[i + 7]) > 78:
                    sum_sd2 += pos[i] * (ord(separated_ref[i + 7]) - 63)
                else:
                    sum_sd2 += pos[i] * (ord(separated_ref[i + 7]) - 64)

        for i in range(4):
            mixt1 += pos[i + 7] * (ord(separated_ref[i + 14]) - 48)

        code_pos1 = (sum_pd1 + mixt1) % 23
        code_pos2 = (sum_sd2 + mixt1) % 23
        code1 = res[code_pos1]
        code2 = res[code_pos2]

        typo = "URBAN" if separated_ref[5].isdigit() else "RURAL"

        if typo == "URBAN":
            raise NotImplementedError(
                "Urban cadastral references are not supported yet. Please check the reference and try again."
            )

        if code1 == separated_ref[18] and code2 == separated_ref[19]:
            logger.info(f"Reference {reference} ({typo}) is valid.")
        else:
            raise ValueError(
                f"Reference {reference} ({typo}) is not valid. Expected control characters: {code1}{code2}, but got {separated_ref[18]}{separated_ref[19]}. Please check the reference and try again."
            )
