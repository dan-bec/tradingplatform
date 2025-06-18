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

def itm_str_prep(itm):
    try:
        return(str(int(itm * 100)))
    except Exception as e:
        print(f"Error fetching data: {e}")
        raise        

def str_to_bool(value):
    if str(value).lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif str(value).lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise ValueError(f"Invalid boolean value: '{value}'")

# Base directory (assumes config.py is in the /scripts folder)
APP_DIR = Path(__file__).parent
APP_NAME = APP_DIR.name
TASKS_DIR = APP_DIR / "tasks"
SCRIPT_DIR = APP_DIR.parent
REPO_ROOT = SCRIPT_DIR.parent
DATA_PATH = REPO_ROOT / "data"

# Common paths used across scripts
FULL_DB_PATH = DATA_PATH / "master_database.db"
PROJECTS_PATH = REPO_ROOT / "projects" / APP_NAME
RAW = "raw_data"
APP_SCHEMA_PREFIX = "ub_"
PREP = "prep"
COMPILED = "compiled"
SEGMENTED = "segmented"
PREP_SCHEMA = APP_SCHEMA_PREFIX + PREP
COMPILED_SCHEMA = APP_SCHEMA_PREFIX + COMPILED
SEGMENTED_SCHEMA = APP_SCHEMA_PREFIX + SEGMENTED

SHARED_DATA_PATH = REPO_ROOT / "src" / "BullseyeApp" / "Shared" / "Data"
GDRIVE_CREDS = SHARED_DATA_PATH / "Credentials.json"
GDRIVE_FOLDER = "1ItSs-28eBoL1zGSKXwoKwnlHTZeQRcJQ"

# OPTION BASELINING
STRICT_OTM = True
MIN_TRADE_VALUE = 3_000
TOP_N_TRADES = 2_000
EXPIRATION_DAYS_OUT = 30
NUMBER_OF_BINS = 3

# SECURITY CLUSTERING
MAX_K = 10

# OPTIMAL ITM
ITM_THRESHOLD = 0.55
ITM_THRESHOLD_100 = itm_str_prep(ITM_THRESHOLD)

def latest_db_date():
    con = duckdb.connect(FULL_DB_PATH) 
    result = con.execute(f"SELECT max(data_date) FROM {PREP_SCHEMA}.filtered_short_term_otm_options_trades;").fetchone()[0] # type: ignore
    result = result.strftime("%Y-%m-%d")
    con.close()
    return result

# OUTPUT PATHS
ITM_PATH = PROJECTS_PATH / latest_db_date() / ITM_THRESHOLD_100
PREP_OUTPUT_DIR = ITM_PATH / PREP
COMPILED_OUTPUT_DIR = ITM_PATH / COMPILED
SEGMENTED_OUTPUT_DIR = ITM_PATH / SEGMENTED
