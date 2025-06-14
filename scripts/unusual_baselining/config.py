from pathlib import Path
from datetime import datetime, timedelta
import duckdb
from functools import lru_cache, wraps

def cache_and_handle_errors(func):
    @lru_cache(maxsize=None)
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error fetching data: {e}")
            raise
    return wrapper

# Base directory (assumes config.py is in the /scripts folder)
APP_DIR = Path(__file__).parent
APP_NAME = APP_DIR.name
TASKS_DIR = APP_DIR / "tasks"
SCRIPT_DIR = APP_DIR.parent
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
PROJECTS_PATH = REPO_ROOT / "projects" / APP_NAME
RAW = "raw_data"
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
ITM_THRESHOLD_100 = str(int(ITM_THRESHOLD*100))

@cache_and_handle_errors
def latest_db_date():
    con = duckdb.connect(FULL_DB_PATH) 
    result = con.execute(f"SELECT max(data_date) FROM {PREP}.filtered_short_term_otm_options_trades;").fetchone()[0] # type: ignore
    result = result.strftime("%Y-%m-%d")
    con.close()
    return result

ITM_PATH = PROJECTS_PATH / latest_db_date() / ITM_THRESHOLD_100
PREP_OUTPUT_DIR = ITM_PATH / PREP
COMPILED_OUTPUT_DIR = ITM_PATH / COMPILED
SEGMENTED_OUTPUT_DIR = ITM_PATH / SEGMENTED