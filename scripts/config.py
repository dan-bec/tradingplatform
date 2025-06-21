from pathlib import Path

# Base directory (assumes config.py is in the /scripts folder)
SCRIPT_DIR = Path(__file__).parent  # /scripts
REPO_ROOT = SCRIPT_DIR.parent  # Repository root directory
DATA_PATH = REPO_ROOT / "data"  # Data directory
FULL_DB_PATH = DATA_PATH / "master_database.db"  # Path to master database
SHARED_DATA_PATH = REPO_ROOT / "src" / "BullseyeApp" / "Shared" / "Data"  # Shared data directory

RAW_SCHEMA = "raw_data"
COMPILED_SCHEMA = "compiled"

DATE_SAMPLE = 250
NUM_LOG_TRADE_VOL_BINS = 3

GDRIVE_CREDS = SHARED_DATA_PATH / "Credentials.json"
GDRIVE_FOLDER = "1ItSs-28eBoL1zGSKXwoKwnlHTZeQRcJQ"