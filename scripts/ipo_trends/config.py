import sys
from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache, wraps

# Determine the project root dynamically
APP_DIR = Path(__file__).parent
REPO_ROOT = APP_DIR.parents[1]  

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config import DATA_PATH, FULL_DB_PATH, SHARED_DATA_PATH, RAW_SCHEMA, COMPILED_SCHEMA, DATE_SAMPLE, NUM_LOG_TRADE_VOL_BINS

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

def num_str_prep(num):
    try:
        return(str(int(num)))
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
APP_NAME = APP_DIR.name
TASKS_DIR = APP_DIR / "tasks"
SCRIPT_DIR = APP_DIR.parent

# Common paths used across scripts
PROJECTS_PATH = REPO_ROOT / "projects" / APP_NAME
APP_SCHEMA_PREFIX = "ipo_"
PREP = "prep"
SEGMENTED = "segmented"
PREP_SCHEMA = APP_SCHEMA_PREFIX + PREP

# IPO PARAMETERS
DAYS_SINCE_IPO = 30
DAYS_SINCE_IPO_STR = num_str_prep(DAYS_SINCE_IPO)
NUMBER_OF_BINS = NUM_LOG_TRADE_VOL_BINS

# SECURITY CLUSTERING
MAX_CLUSTERS = 10

# OPTIMAL ITM

  
# OUTPUT PATHS
IPO_PATH = PROJECTS_PATH / DAYS_SINCE_IPO_STR
PREP_OUTPUT_DIR = IPO_PATH / PREP
COMPILED_OUTPUT_DIR = IPO_PATH / COMPILED_SCHEMA
SEGMENTED_OUTPUT_DIR = IPO_PATH / SEGMENTED

IPO_PATH.mkdir(parents=True, exist_ok=True)
PREP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
COMPILED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SEGMENTED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)