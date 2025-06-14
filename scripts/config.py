from pathlib import Path
from datetime import datetime

# Base directory (assumes config.py is in the /scripts folder)
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent

# Common paths used across scripts
S3_ENDPOINT = "https://files.polygon.io"  # Polygon S3-compatible endpoint
BUCKET_NAME = "flatfiles"  # Polygon bucket name
DATASERVICES_PATH = REPO_ROOT / "src" / "BullseyeApp" / "Shared" / "Data" / "DataService.cs"
DATA_PATH = REPO_ROOT / "data"
FULL_DB_PATH = DATA_PATH / "master_database.db"
PROJECTS_PATH = REPO_ROOT / "projects"
PREP = "prep"
PREP_OUTPUT_DIR = PROJECTS_PATH / PREP
COMPILED = "compiled"
COMPILED_OUTPUT_DIR = PROJECTS_PATH / COMPILED
SEGMENTED_DIR = PROJECTS_PATH / "segmented"
STOCK_SUMMARY_DIR = DATA_PATH / "stocks" / "daily"
OPTION_TRADE_DIR = DATA_PATH / "options" / "trades"
SECTORS_CSV = DATA_PATH / "stocks" / "sectors_industries.csv"

# RAW DATA LOAD
START_DATE = str(datetime(2024, 8, 1).date())
END_DATE = str(datetime.now().date())  # Updated to include today
NUM_FILES_TO_PROCESS = 200

# OPTION BASELINING
STRICT_OTM = True
MIN_TRADE_VALUE = 3_000
TOP_N_TRADES = 2_000
EXPIRATION_DAYS_OUT = 30
NUMBER_OF_BINS = 20

# SECURITY CLUSTERING
MAX_K = 10

# OPTIMAL ITM
ITM_THRESHOLD = 0.55