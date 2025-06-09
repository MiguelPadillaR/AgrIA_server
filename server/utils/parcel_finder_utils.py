from sigpac_tools.find import find_from_cadastral_registry

def find_parcel_by_cadastral_reference(cadastral_reference: str):
    """
    Finds a parcel by its cadastral reference using the sigpac_tools library.
    
    Args:
        cadastral_reference (str): The cadastral reference of the parcel to find.
    
    Returns:
        dict: A dictionary containing the parcel information if found, otherwise None.
    """
    try:
        # Use the find_from_cadastral_registry function to get parcel information
        geometry, metadata = find_from_cadastral_registry(cadastral_reference)
        return geometry, metadata
    except Exception as e:
        print(f"Error finding parcel with cadastral reference {cadastral_reference}: {e}")
        return None

def get_s2dr3_image(date: str, geometry: dict):
    """    Retrieves the S2DR3 image for a given date and geometry.
    Args:
        date (str): The date for which to retrieve the S2DR3 image.
        geometry (dict): The geometry of the area for which to retrieve the image.
    Returns:
        TODO
    """
    return "This function is not implemented yet. Please implement the logic to retrieve the S2DR3 image based on the geometry and date."