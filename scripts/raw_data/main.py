import argparse
from datetime import datetime
import time
import config as config
from tasks.download_data import main as download_main
from tasks.raw_data_load import main as load_main

def main():

    parser = argparse.ArgumentParser(description="Run all scripts with specified parameters")
    parser.add_argument("--start-date", type=str, default=config.START_DATE, help="Start date (YYYY-MM-DD), defaults to config.START_DATE")
    parser.add_argument("--end-date", type=str, default=config.END_DATE, help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--num-files-to-load", type=int, default=config.NUM_FILES_TO_PROCESS, help="Number of files to load, defaults to config.NUM_FILES_TO_PROCESS")

    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date if args.end_date is not None else datetime.now().strftime("%Y-%m-%d")
    num_files_to_load = args.num_files_to_load

    download_main(start_date, end_date)
    load_main(num_files_to_load)

if __name__ == "__main__":
    start_time = time.time()
    print(f"Main Start time: {start_time:.2f} seconds")

    main()

    end_time = time.time()
    print(f"Main End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Main Execution time: {duration:.2f} seconds")
