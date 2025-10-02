import pathlib as Path
import os

from ...config.constants import SEN2SR_SR_DIR

CURR_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CURR_SCRIPT_DIR = Path.Path(CURR_SCRIPT_DIR)

MODEL_DIR = str(CURR_SCRIPT_DIR / "model")
PNG_DIR = SEN2SR_SR_DIR / "png"
TIF_DIR = SEN2SR_SR_DIR / "tif"

OG_TIF_FILEPATH = TIF_DIR / "original.tif"
SR_TIF_FILEPATH = TIF_DIR / "superres.tif"

OG_PNG_FILEPATH = str(OG_TIF_FILEPATH).replace("tif", "png")
SR_PNG_FILEPATH = str(SR_TIF_FILEPATH).replace("tif", "png")
COMPARISON_PNG_FILEPATH = PNG_DIR / "comparison.png"

GEOJSON_FILEPATH = SEN2SR_SR_DIR / "polygon.geojson"