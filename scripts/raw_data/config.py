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

from scripts.config import DATA_PATH, FULL_DB_PATH, SHARED_DATA_PATH, RAW_SCHEMA

# Base directory (assumes config.py is in the /scripts folder)
APP_NAME = APP_DIR.name
TASKS_DIR = APP_DIR / "tasks"

# Common paths used across scripts
S3_ENDPOINT = "https://files.polygon.io"  # Polygon S3-compatible endpoint
BUCKET_NAME = "flatfiles"  # Polygon bucket name
SHARED_DATA_PATH = REPO_ROOT / "src" / "BullseyeApp" / "Shared" / "Data"
DATASERVICES_PATH = SHARED_DATA_PATH / "DataService.cs"

STOCK_SUMMARY_DIR = DATA_PATH / "stocks" / "daily"
STOCK_TRADE_DIR = DATA_PATH / "stocks" / "trades"
OPTION_SUMMARY_DIR = DATA_PATH / "options" / "daily"
OPTION_TRADE_DIR = DATA_PATH / "options" / "trades"
SECTORS_CSV = DATA_PATH / "stocks" / "sectors_industries.csv"

# RAW DATA LOAD
START_DATE = str(datetime.now().date() - timedelta(days=2*365))
END_DATE = str(datetime.now().date())  # Updated to include today
NUM_FILES_TO_PROCESS = 500