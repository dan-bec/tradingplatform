import sys
from pathlib import Path

# Determine the project root dynamically
FILE_DIR = Path(__file__)
APP_DIR = FILE_DIR.parent
REPO_ROOT = APP_DIR.parents[1]  
FILE_NAME = FILE_DIR.relative_to(REPO_ROOT)

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from datetime import datetime
import time
import scripts.raw_data.config as config
from scripts.raw_data.tasks.download_data import main as download_main
from scripts.raw_data.tasks.raw_data_load import main as load_main
from scripts.raw_data.tasks.average_true_range import main as atr_main

def main(start_date, end_date, num_files_to_load, batch_size):
    # Capture and print start time
    start_time = time.time()
    print(f"!{FILE_NAME}! Start time: {start_time:.2f} seconds")

    download_main(start_date, end_date)
    load_main(num_files_to_load, batch_size)
    atr_main()

    # Print execution time
    end_time = time.time()
    print(f"!{FILE_NAME}! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!{FILE_NAME}! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run all scripts with specified parameters")
    parser.add_argument("--start-date", type=str, default=config.START_DATE, help="Start date (YYYY-MM-DD), defaults to config.START_DATE")
    parser.add_argument("--end-date", type=str, default=config.END_DATE, help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--num-files-to-load", type=int, default=config.NUM_FILES_TO_PROCESS, help="Number of files to load, defaults to config.NUM_FILES_TO_PROCESS")
    parser.add_argument("--batch-size", type=int, default=config.BATCH_SIZE)
    args = parser.parse_args()

    end_date = args.end_date if args.end_date is not None else datetime.now().strftime("%Y-%m-%d")

    main(args.start_date, end_date, args.num_files_to_load, args.batch_size)
