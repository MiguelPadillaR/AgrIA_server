from pathlib import Path
import os

from flask import json

from ...config.constants import BASE_PROMPTS_PATH

BM_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

BM_PROMPT_LIST_FILE = BM_DIR / "prompt_list.json"
BM_SR_IMAGES_DIR = BM_DIR / "sr_images"
BM_LLM_DIR = BM_DIR / "llm_formatted_out"
BM_JSON_DIR = BM_DIR / "in_out"

OG_ROLE_FILEPATH = BASE_PROMPTS_PATH / "LLM-role_prompt.txt"
OG_CLASSIFICATION_FILEPATH = BASE_PROMPTS_PATH / "classification.json"
BM_PROMPT_LIST_DATA = {
    "description": "Initial setup prompts for the Gemini model",
    "examples": {
        "name": "examples",
        "examples": "response_examples"
    }
}

# (Optional) write to file:
with BM_PROMPT_LIST_FILE.open("w") as f:
    json.dump(BM_PROMPT_LIST_DATA, f, indent=4)

# AgrIA Paper data
CADASTRAL_REF_LIST_PAPER = ["26002A001000010000EQ", "41004A033000290000IG","46113A023000420000RL", "06900A766000030000WA"]
DATES_PAPER = ["2025-6-6", "2025-4-5", "2024-3-22", "2024-10-21"]
USE_PAPER_DATA = False

# Ecoschemes classification data
CLASSIFICATION_OUT_DIR = BM_DIR / "classif_out"

LANG = "en"

FULL_DESC_SYS_INSTR_EN = """## GENERATION DIRECTIVES FOR STRUCTURED MARKDOWN REPORT

**GOAL:** Generate a single, comprehensive "EcoScheme Payment Estimate" report in Markdown (MD) format by strictly merging the provided calculated JSON data, the pre-generated Description text, and the pre-generated Clarifications text. The LLM's task is **MAPPING and RENDERING**, not generating the core analysis (Description/Clarifications).

### I. REPORT STRUCTURE AND FORMATTING
1.  **Structure:** The final report **MUST** contain four sections in this order: `DESCRIPTION`, `POSSIBLE ECO-SCHEMES`, `ESTIMATED TOTAL PAYMENT`, and `RESULTS`.
2.  **Language:** Render the report in the same language as the initial user prompt (e.g., if the user prompts in English, use English table headers and text).
3.  **Visual:** Use the exact Markdown table formatting, headings, bolding, and horizontal rules (`---`) as shown in the provided examples.

### II. GEOGRAPHICAL CONTEXT AND DEFAULTS
1.  **Default Region:** All initial reports must use **Peninsular** rates for calculated totals and table values, as defined by the `Calculation_Context.Rate_Applied`.
2.  **Context Switching:** If the user explicitly asks to view the results for the **Insular** region, use the corresponding values under the `"Insular"` key in the JSON for the tables and totals.

### III. DATA MAPPING RULES

| MD SECTION | DATA SOURCE (JSON Key) | MAPPING/RULE |
| :--- | :--- | :--- |
| **DESCRIPTION** | *Pre-Generated Description Text* | Insert the full text. Ensure `Total_Parcel_Area_ha` is correctly inserted if it was a placeholder in the text. |
| **POSSIBLE ECO-SCHEMES** | `Estimated_Total_Payment` (Iterate all) | Use this format for the Ecoscheme column: `Ecoscheme_ID` - `Ecoscheme_Name` (`Ecoscheme_Subtype` if there is one). Use `Peninsular/Insular.Applied_Base_Payment_EUR` for the rate columns. Use the relevant scheme from the **Classification Data** for `Conditions` and `Pluriannuality Bonus`. |
| **ESTIMATED TOTAL PAYMENT**| `Estimated_Total_Payment` (Iterate all) | Use **Peninsular** values for `Total_Base_Payment_EUR` and `Total_with_Pluriannuality_EUR`. Use `Peninsular.Applicable` for the 'Applicable' column. |
| **RESULTS (Summary Table)**| `Final_Results` | Join `Applicable_Ecoschemes` with a plus sign (`+`). Use `Total_Aid_without_Pluriannuality_EUR` and `Total_Aid_with_Pluriannuality_EUR` for the totals. |
| **RESULTS (Clarifications)**| *Pre-Generated Clarifications Text* | Insert the entire bulleted list of pre-generated clarifications verbatim into the `RESULTS` section. |
"""

FULL_DESC_SYS_INSTR_ES = """## Instrucciones Concisas para el LLM

Para que el LLM pueda replicar con precisión este formato, se recomienda el siguiente conjunto de instrucciones, que asume que el LLM recibirá el JSON de datos y un texto pre-generado para la **Descripción** y las **Aclaraciones** (en el idioma deseado).

### **DIRECTIVAS DE GENERACIÓN DE INFORMES (ESPAÑOL)**

**Objetivo:** Generar un informe completo y estructurado en Markdown (MD) en español, fusionando el JSON de cálculo (`Input JSON`) con textos pre-generados (`Descripción` y `Aclaraciones`).

**REGLAS DE FORMATO:**
1.  **Idioma:** Output **solo** en español.
2.  **Estructura:** Seguir estrictamente el orden y formato de las cuatro secciones: `DESCRIPCIÓN`, `ECORREGÍMENES POSIBLES`, `PAGO TOTAL ESTIMADO`, y `RESULTADOS`.

**MAPEO DE DATOS:**

| SECCIÓN MD | ORIGEN DEL DATO (JSON Key) | MAPEO/REGLA |
| :--- | :--- | :--- |
| **DESCRIPCIÓN** | `Total_Parcel_Area_ha` y *Texto de Descripción Pre-Generado* | **REGLA:** Insertar el texto pre-generado completo. Asegurar que el valor exacto de **`Total_Parcel_Area_ha`** se inserte en el texto si contiene un marcador. |
| **ECORREGÍMENES POSIBLES** | `Estimated_Total_Payment` (Iterar todos) y `Datos de Clasificación` | **Formato Ecorégimen:** **`Ecoscheme_ID`** - **`Ecoscheme_Name`** (**`Ecoscheme_Subtype`** si no es nulo). Usar **`Peninsular/Insular.Applied_Base_Payment_EUR`** para las columnas de tasa. Usar los **`Datos de Clasificación`** para el texto de `Condiciones` y `Complemento Plurianualidad`. |
| **PAGO TOTAL ESTIMADO** | `Estimated_Total_Payment` (Iterar todos) | **REGLA:** Usar **solo** los valores **Peninsular** para **`Total_Base_Payment_EUR`** y **`Total_with_Pluriannuality_EUR`**. Usar **`Peninsular.Applicable`** para la columna 'Aplicable'. |
| **RESULTADOS (Tabla Resumen)** | `Final_Results` | **REGLA:** Unir **`Final_Results.Applicable_Ecoschemes`** con un signo de suma (`+`) para el título de la fila. Usar **`Total_Aid_without_Pluriannuality_EUR`** y **`Total_Aid_with_Pluriannuality_EUR`** para los totales. |
| **RESULTADOS (Aclaraciones)** | *Texto de Aclaraciones Pre-Generado* | **REGLA:** Insertar la lista de puntos de las aclaraciones pre-generadas textualmente en la sección `RESULTADOS`. |

**REGLA DE CONTEXTO GEOGRÁFICO:** El informe inicial debe usar las tasas **Peninsulares**. Si el usuario solicita un cambio a la región **Insular**, el LLM debe regenerar las tablas `ECORREGÍMENES POSIBLES` y `PAGO TOTAL ESTIMADO` utilizando los valores de la clave `"Insular"`.

 Fuente: Importes Unitarios Provisionales, Campaña PAC 2025.
 """