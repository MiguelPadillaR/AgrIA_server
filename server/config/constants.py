from pathlib import Path
import json

MODEL_NAME = "gemini-2.0-flash-lite"
BASE_CONTEXT_PATH = Path("./assets/LLM_assets/context")
BASE_PROMPTS_PATH = Path("./assets/LLM_assets/prompts")

CONTEXT_DOCUMENTS_FILE = "context_document_links.json"
PROMPT_LIST_FILE = "prompt_list.json"

TEMP_DIR = Path('temp/')

EXCLUSIVITY_RULE = """\n\n
**CRITICAL EXCLUSIVITY DIRECTIVE FOR CALCULATION:**
**UNBREAKABLE CAP RULE:** Ecoscheme aid is **MUTUALLY EXCLUSIVE**. Each hectare of land (Land Use) can only be assigned to **ONE SINGLE** Ecoscheme (ES).
When calculating the amounts, if a Land Use (e.g., TA, OV, VI) is eligible for multiple ES, you must:
    1. **Identify** the ES that offers the **HIGHEST TOTAL AMOUNT (€/ha)**, including the pluriannuality supplement if applicable, to choose the most beneficial option.
    2. **Assign** the total area of that Land Use **exclusively** to that ES in the calculation table.
    3. For alternative ES that share the same Land Use (e.g., P5 vs P6/P7 for OV), mark the `Applicable` column with the text: **"Excluded: [Land use ID] used for [Chosen ES]"**.
    4. **NEVER** sum the payments from multiple ES for the same land area.
    """

CALCULATIONS_RULE = """\n\n
**TIERED CALCULATION RULE:**
If the 'Rates' object contains 'Tier_1' (`Tramo_1` in Spanish) and 'Tier_2' (`Tramo_2` in Spanish) keys:
    1.  Identify the **Threshold_ha** (L) from the 'Rates' object. Below or equal to this area, use Tier 1; above it, use Tier 2.
    2.  If Total Area ≤ L:
            Base Payment = Total Area * Tier_1
        Else:
            Base Payment = Total Area * Tier_2
    3.  If the 'Pluriannuality' field is 'Applicable', add the fixed bonus of **25.00 €/ha** (as defined in the system instructions) to the Total Area for the 'Total with Pluriannuality' column.
"""

FULL_DESC_TRIGGER = '###DESCRIBE_LONG_IMAGE###'
SHORT_DESC_TRIGGER = '###DESCRIBE_SHORT_IMAGE###'

MIME_TYPES = {
    'txt': 'text/plain',
    'md': 'text/markdown',
    'pdf': 'application/pdf',
    'json': 'application/json',
    'csv': 'text/csv',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'jpg': 'image/jpeg',
    'png': 'image/png',
}

SPAIN_JSON = Path("./assets/geojson_assets/spain.json")
with open(SPAIN_JSON, 'r') as file:
    SPAIN_ZONES = json.load(file)

ANDALUSIA_TILES = ["29SPC", "29SQC", "30STH", "30SUH", "30SVH", "30SWH", "30SXH", "30SYH", "30SXG", 
        "30SWG", "30SVG", "30SUG", "30STG", "29SQB" ,"29SPB", "30STF", "30SUF", 
        "30SVF", "30SWF"]

SR_BANDS = ["B02", "B03", "B04", "B08"]
BANDS_DIR = TEMP_DIR / "bands"
MERGED_BANDS_DIR = TEMP_DIR / "merged_bands"
MASKS_DIR = TEMP_DIR / "masks"
SR5M_DIR = TEMP_DIR / "sr_5m"
RESOLUTION = 10

SEN2SR_SR_DIR = TEMP_DIR / "sr_2.5m"

GET_SR_BENCHMARK = False

if GET_SR_BENCHMARK:
    print("⚠️  WARNING: SUPER-RES BENCHMARK IS ACTIVE. This will execute both SR4S and SEN2SR pipelines (in that order), which will slow down all parcel fetching processes. To deactivate it, set the `GET_SR_BENCHMARK` to `False` in the `Agria_server/server/config/constants.py` file")
