import os
from server.config.constants import TEMP_DIR

def save_image_and_get_path(file) -> str:
    """
    Stores file in server's local temp dir
    Arguments:
        file (File): Image file to store.
    Returns:
        filepath (str): Path of the stored image.
    """
    upload_dir = TEMP_DIR
    os.makedirs(upload_dir, exist_ok=True)
    filename = file.filename
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    return filepath

def generate_image_context_data(image_date, land_uses, query) -> str:
    """
    Retrieves image context data for prompt generation.
    Generates both English and Spanish versions and saves them as text files.
    
    Args:
        image_date (str): Date of the image.
        land_uses (list[dict]): Land use metadata.
        query (list[dict]): List all parcels' detailed info. present in the state.
    
    Returns:
        dict: {"es": str, "en": str} with Spanish and English context data.
    """
    try: 
        # Define templates for both languages
        templates = {
            "es": {
                "header": f"\nFECHA DE IMAGEN: {image_date}\nTIPOS DE USO DETECTADAS: {len(land_uses)}\n",
                "parcel": "\n- Tipo de Uso: {type}\n- Superficie admisible (ha): {surface}\n- Coef. de Regadío: {irrigation}%\n",
                "slope": "- Pendiente media: {slope}%\n",
                "footer": "\nSUPERFICIE ADMISIBLE TOTAL (ha): {total}"
            },
            "en": {
                "header": f"\nIMAGE DATE: {image_date}\nLAND USES DETECTED: {len(land_uses)}\n",
                "parcel": "\n- Land Use: {type}\n- Eligible surface (ha): {surface}\n- Irrigation Coeficient: {irrigation}%\n",
                "slope": "- Slope Coeficient: {slope}%\n",
                "footer": "\nTOTAL ELIGIBLE SURFACE (ha): {total}"
            }
        }

        results = {"es": templates["es"]["header"], "en": templates["en"]["header"]}
        total_surface = 0.0

        for use in land_uses:
            land_use_type = use["uso_sigpac"]
            surface = float(use.get("superficie_admisible") or use.get("dn_surface", 0))

            total_surface += surface
            irrigation_coef, slope_coef = get_coefficients(query, land_use_type)

            for lang in ["es", "en"]:
                results[lang] += templates[lang]["parcel"].format(type=land_use_type, surface=surface, irrigation=round(irrigation_coef, 2))
                if slope_coef > 0:
                    results[lang] += templates[lang]["slope"].format(slope=round(slope_coef, 2))

        for lang in ["es", "en"]:
            results[lang] += templates[lang]["footer"].format(total=round(total_surface, 3))
            desc_file = TEMP_DIR / f"parcel_desc-{lang}.txt"
            print(f"\nGenerating file: {desc_file}")
            with open(desc_file, "w") as file:
                file.write(results[lang])

        return results
    except Exception as e:
        print("Error while getting image context data: " + e)

def get_coefficients(query, land_use)-> float:
    """
    Returns the mean irrigation and slope coefficient across all parcels in state for the specified land use.

    Arguments:
        query(list[dict]): List all parcels' detailed info. present in the state.
        land_use (str): Land use type
    Returns:
        coefs (tuple(float)): Mean irrigation and slope coefficient for the land use.
    """
    woody_crops_list = ["CF", "CI", "CS", "CV", "FF", "FL", "FS", "FV", "FY", "OC", "OF", "OV", "VF", "VI", "VO"]
    irrigation_coef = 0.0
    slope_coef = 0.0
    parcels_with_land_use = 0

    for parcel in query:
        if parcel.get("uso_sigpac") == land_use:
            value = parcel.get("coef_regadio")
            irrigation_coef += float(value) if value is not None else 0.0
            # Get slope for woody crops only
            if land_use.split("-")[0].replace(" ", "") in woody_crops_list:
                value = parcel.get("pendiente_media")
                slope_coef += float(value) if value is not None else 0.0
            parcels_with_land_use += 1

    mean_irrigation_coef = irrigation_coef / parcels_with_land_use if parcels_with_land_use > 0 else 0.0
    mean_slope_coef = slope_coef / parcels_with_land_use if parcels_with_land_use > 0 else 0.0

    return mean_irrigation_coef, mean_slope_coef