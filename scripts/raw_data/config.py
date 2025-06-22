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

from scripts.config import DATA_PATH, FULL_DB_PATH, SHARED_DATA_PATH, RAW_SCHEMA, DATE_SAMPLE

# Base directory (assumes config.py is in the /scripts folder)
APP_NAME = APP_DIR.name
TASKS_DIR = APP_DIR / "tasks"

# Common paths used across scripts
S3_ENDPOINT = "https://files.polygon.io"  # Polygon S3-compatible endpoint
BUCKET_NAME = "flatfiles"  # Polygon bucket name
SHARED_DATA_PATH = REPO_ROOT / "src" / "BullseyeApp" / "Shared" / "Data"
DATASERVICES_PATH = SHARED_DATA_PATH / "DataService.cs"

POLYGON_DAILY = "daily"
POLYGON_TRADES = "trades"
POLYGON_QUOTES = "quotes"
POLYGON_MINUTE = "minute"

STOCKS_DIR = DATA_PATH / "stocks"
STOCK_SUMMARY_DIR = STOCKS_DIR / POLYGON_DAILY
STOCK_TRADE_DIR = STOCKS_DIR / POLYGON_TRADES
STOCK_QUOTES_DIR = STOCKS_DIR / POLYGON_QUOTES
STOCK_MINUTE_DIR = STOCKS_DIR / POLYGON_MINUTE
SECTORS_CSV = STOCKS_DIR / "sectors_industries.csv"

OPTIONS_DIR = DATA_PATH / "options"
OPTION_SUMMARY_DIR = OPTIONS_DIR / POLYGON_DAILY
OPTION_TRADE_DIR = OPTIONS_DIR / POLYGON_TRADES
OPTION_QUOTES_DIR = OPTIONS_DIR / POLYGON_QUOTES
OPTION_MINUTE_DIR = OPTIONS_DIR / POLYGON_MINUTE

# RAW DATA LOAD
START_DATE = str(datetime.now().date() - timedelta(days=2*365))
END_DATE = str(datetime.now().date())  # Updated to include today
NUM_FILES_TO_PROCESS = DATE_SAMPLE
BATCH_SIZE = 100