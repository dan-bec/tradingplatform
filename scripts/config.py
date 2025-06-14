from pathlib import Path
from datetime import datetime, timedelta

# Base directory (assumes config.py is in the /scripts folder)
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent

# Common paths used across scripts
S3_ENDPOINT = "https://files.polygon.io"  # Polygon S3-compatible endpoint
BUCKET_NAME = "flatfiles"  # Polygon bucket name
SHARED_DATA_PATH = REPO_ROOT / "src" / "BullseyeApp" / "Shared" / "Data"
DATASERVICES_PATH = SHARED_DATA_PATH / "DataService.cs"
GDRIVE_CREDS = SHARED_DATA_PATH / "Credentials.json"
GDRIVE_FOLDER = "1ItSs-28eBoL1zGSKXwoKwnlHTZeQRcJQ"
DATA_PATH = REPO_ROOT / "data"
FULL_DB_PATH = DATA_PATH / "master_database.db"
PROJECTS_PATH = REPO_ROOT / "projects"
PREP = "prep"
COMPILED = "compiled"
SEGMENTED = "segmented"

STOCK_SUMMARY_DIR = DATA_PATH / "stocks" / "daily"
OPTION_TRADE_DIR = DATA_PATH / "options" / "trades"
SECTORS_CSV = DATA_PATH / "stocks" / "sectors_industries.csv"

# RAW DATA LOAD
START_DATE = str(datetime.now().date() - timedelta(days=365))
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
ITM_THRESHOLD = 0.75
PREP_OUTPUT_DIR = PROJECTS_PATH / str(int(ITM_THRESHOLD*100)) / PREP
COMPILED_OUTPUT_DIR = PROJECTS_PATH / str(int(ITM_THRESHOLD*100)) / COMPILED
SEGMENTED_OUTPUT_DIR = PROJECTS_PATH / str(int(ITM_THRESHOLD*100)) / SEGMENTED