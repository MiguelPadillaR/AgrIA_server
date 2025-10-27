from pathlib import Path
import os

BM_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
BM_DATA_DIR = BM_DIR / "data"
BM_SR_DIR = BM_DATA_DIR / "models_out"
BM_RES_DIR = BM_DIR / "res"