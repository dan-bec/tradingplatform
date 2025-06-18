import sys
from pathlib import Path

# Determine the project root dynamically
APP_DIR = Path(__file__).parent
REPO_ROOT = APP_DIR.parents[1]  

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config import DATA_PATH, FULL_DB_PATH, SHARED_DATA_PATH, RAW_SCHEMA
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

# Common paths used across scripts
PROJECTS_PATH = REPO_ROOT / "projects" / APP_NAME
APP_SCHEMA_PREFIX = "pca_"
PREP = "prep"
COMPILED = "compiled"
SEGMENTED = "segmented"
PREP_SCHEMA = APP_SCHEMA_PREFIX + PREP
COMPILED_SCHEMA = APP_SCHEMA_PREFIX + COMPILED
SEGMENTED_SCHEMA = APP_SCHEMA_PREFIX + SEGMENTED

# PUT CALL THRESHOLDS
MIN_TRADE_VALUE = 3_000
SHORT_TERM_DAYS_OUT = 30
MEDIUM_TERM_DAYS_OUT = 60
LONG_TERM_DAYS_OUT = 90
# EXPIRATION_DAYS_OUT = 180
NUMBER_OF_BINS = 3
ROLLING_WINDOW = 50

# SECURITY CLUSTERING
MAX_K = 10

@cache_and_handle_errors
def latest_db_date():
    static_date = "1900-01-01"  # Define the static fallback date
    with duckdb.connect(FULL_DB_PATH) as con:
        try:
            result = con.execute(f"SELECT max(data_date) FROM {PREP_SCHEMA}.agg_filtered_options_trades").fetchone()[0] # type: ignore
            if result is not None:
                return result.strftime("%Y-%m-%d")
            else:
                return static_date
        except duckdb.CatalogException:
            return static_date

# OUTPUT PATHS
LATEST_PATH = PROJECTS_PATH / 'latest'
PCA_PATH = PROJECTS_PATH / latest_db_date()
PREP_OUTPUT_DIR = PCA_PATH / PREP
COMPILED_OUTPUT_DIR = PCA_PATH / COMPILED
SEGMENTED_OUTPUT_DIR = PCA_PATH / SEGMENTED
