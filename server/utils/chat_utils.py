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

def generate_image_context_data(image_date, land_uses) -> str:
    """
    Retrieves image context data for prompt generation.
    Generates both English and Spanish versions and saves them as text files.
    
    Args:
        image_date (str): Date of the image.
        land_uses (list[dict]): Land use metadata.
    
    Returns:
        dict: {"es": str, "en": str} with Spanish and English context data.
    """
    try: 
        # Define templates for both languages
        templates = {
            "es": {
                "header": f"FECHA DE IMAGEN: {image_date}\nPARCELAS DETECTADAS: {len(land_uses)}\n",
                "parcel": "\n- Tipo de Uso: {type}\n- Superficie admisible (ha): {surface}\n",
                "footer": "\nSUPERFICIE ADMISIBLE TOTAL (ha): {total}"
            },
            "en": {
                "header": f"IMAGE DATE: {image_date}\nPARCELS DETECTED: {len(land_uses)}\n",
                "parcel": "\n- Land Use: {type}\n- Eligible surface (ha): {surface}\n",
                "footer": "\nTOTAL ELIGIBLE SURFACE (ha): {total}"
            }
        }

        results = {"es": templates["es"]["header"], "en": templates["en"]["header"]}
        total_surface = 0.0

        for use in land_uses:
            type_ = use["uso_sigpac"]
            surface = round(float(use.get("superficie_admisible") or use.get("dn_surface", 0))/10000, 5)

            total_surface += surface

            for lang in ["es", "en"]:
                results[lang] += templates[lang]["parcel"].format(type=type_, surface=surface)

        for lang in ["es", "en"]:
            results[lang] += templates[lang]["footer"].format(total=round(total_surface, 3))
            desc_file = TEMP_DIR / f"parcel_desc-{lang}.txt"
            print(f"\nGenerating file:\t{desc_file}")
            with open(desc_file, "w") as file:
                file.write(results[lang])

        return results
    except Exception as e:
        print("Error while getting image context data: " + e)

