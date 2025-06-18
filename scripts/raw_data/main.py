import argparse
import subprocess
from datetime import datetime
import time
import config as config
import logging
from pathlib import Path

def run_script(script_name, args_list):
    """Helper function to run a script with given arguments."""
    cmd = ["python3", config.APP_DIR / script_name] + args_list
    subprocess.run(cmd, check=True)

def main():
    # Capture and print start time
    start_time = time.time()
    print(f"Main Start time: {start_time:.2f} seconds")

    # Define command-line arguments
    parser = argparse.ArgumentParser(description="Run all scripts with specified parameters")
    parser.add_argument("--start-date", type=str, default=config.START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=config.END_DATE, help="End date (YYYY-MM-DD)")
    parser.add_argument("--num-files-to-load", type=int, default=config.NUM_FILES_TO_PROCESS, help="Number of files to load")

    args = parser.parse_args()

    # Set end_date to today if not provided
    end_date = args.end_date if args.end_date else datetime.now().strftime("%Y-%m-%d")

    # Run scripts in order with appropriate arguments
    run_script("tasks/0_download_data.py", ["--start-date", args.start_date, "--end-date", end_date])

    run_script("tasks/1_raw_data_load.py", [
        "--num-files-to-load", str(args.num_files_to_load)
    ])

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"Main Start time: {start_time:.2f} seconds")

    main()

    # Print execution time
    end_time = time.time()
    print(f"Main End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Main Execution time: {duration:.2f} seconds")