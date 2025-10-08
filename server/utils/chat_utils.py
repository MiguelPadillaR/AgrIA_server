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

def generate_image_context_data(image_date, image_crops, language) -> str:
    """
    Retrieves image context data for prompt generation.
    Generates both English and Spanish versions and saves them as text files.
    
    Args:
        image_date (str): Date of the image.
        image_crops (list[dict]): Crop metadata.
    
    Returns:
        dict: {"es": str, "en": str} with Spanish and English context data.
    """
    try: 
        # Define templates for both languages
        templates = {
            "es": {
                "header": f"FECHA DE IMAGEN: {image_date}\nPARCELAS DETECTADAS: {len(image_crops)}\n",
                "parcel": "\n- Recinto: {id}\n- Tipo: {type}\n- Superficie admisible (m2): {surface}\n",
                "irrigation": "- Coef. regadío: {irrigation}%\n",
                "footer": "\nSUPERFICIE ADMISIBLE TOTAL (m2): {total}"
            },
            "en": {
                "header": f"IMAGE DATE: {image_date}\nPARCELS DETECTED: {len(image_crops)}\n",
                "parcel": "\n- Parcel ID: {id}\n- Type: {type}\n- Eligible surface (m2): {surface}\n",
                "irrigation": "- Irrigation coefficient: {irrigation}%\n",
                "footer": "\nTOTAL ELIGIBLE SURFACE (m2): {total}"
            }
        }

        results = {"es": templates["es"]["header"], "en": templates["en"]["header"]}
        total_surface = 0.0

        for crop in image_crops:
            parcel_id = crop["recinto"]
            type_ = crop["uso_sigpac"]
            surface = round(float(crop.get("superficie_admisible") or crop.get("dn_surface", 0)), 3)
            irrigation = crop.get("coef_regadio") or 0
            total_surface += surface

            for lang in ["es", "en"]:
                results[lang] += templates[lang]["parcel"].format(id=parcel_id, type=type_, surface=surface)
                if irrigation > 0:
                    results[lang] += templates[lang]["irrigation"].format(irrigation=irrigation)

        for lang in ["es", "en"]:
            results[lang] += templates[lang]["footer"].format(total=round(total_surface, 3))
            desc_file = TEMP_DIR / f"parcel_desc-{lang}.txt"
            print(f"\nGenerating file:\t{desc_file}")
            with open(desc_file, "w") as file:
                file.write(results[lang])

        return results
    except Exception as e:
        print("Error while getting image context data: " + e)

