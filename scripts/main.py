import sys
from pathlib import Path

# Determine the project root dynamically
FILE_DIR = Path(__file__)
APP_DIR = FILE_DIR.parent
REPO_ROOT = APP_DIR.parent
FILE_NAME = FILE_DIR.relative_to(REPO_ROOT)

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
    
import multiprocessing
import subprocess
from raw_data.main import main as run_raw_data
from unusual_baselining.main import main as run_unusual_baselining
from put_call_anomalies.main import main as run_put_call_anomalies
import config
import raw_data.config as raw_config
import unusual_baselining.config as ub_config
import put_call_anomalies.config as pca_config
import upload_to_drive as upload_to_drive
import logging
from datetime import datetime
import time


def bool_type(value):
    try:
        return ub_config.str_to_bool(value)
    except ValueError as e:
        raise ValueError(f"Invalid boolean value: '{value}'")

import subprocess
from datetime import datetime
import config  # Assuming config contains REPO_ROOT

def push_to_github():
    repo_root = config.REPO_ROOT
    try:
        # Add all changes
        result = subprocess.run(["git", "-C", repo_root, "add", "."], check=True, capture_output=True, text=True)
        print(f"Git add output: {result.stdout}")
        
        # Check if there are changes to commit
        status = subprocess.run(["git", "-C", repo_root, "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout:
            print("No changes to commit.")
            return
        
        # Commit changes
        commit_message = f"Update outputs {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        result = subprocess.run(["git", "-C", repo_root, "commit", "-m", commit_message], check=True, capture_output=True, text=True)
        print(f"Git commit output: {result.stdout}")
        
        # Get current branch
        current_branch = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True
        ).stdout.strip()
        print(f"Pushing to branch: {current_branch}")
        
        # Push to remote
        result = subprocess.run(
            ["git", "-C", repo_root, "push", "origin", current_branch],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Git push output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e.cmd}")
        print(f"Error output: {e.stderr}")
        raise

def push_to_drive():
    # Authenticate with Google Drive
    service = upload_to_drive.authenticate_google_drive(config.GDRIVE_CREDS)
    if service is None:
        logging.error("Failed to authenticate with Google Drive. Skipping upload.")
        return
    
    # Define target folder and create a date-based subfolder
    target_folder_id = "1ItSs-28eBoL1zGSKXwoKwnlHTZeQRcJQ"  # Replace with your folder ID
    date_folder_name = datetime.now().strftime("%Y-%m-%d")
    date_folder_id = upload_to_drive.create_folder(service, date_folder_name, target_folder_id)
    
    if date_folder_id is None:
        logging.error("Failed to create date folder. Skipping upload.")
        return
    
    # Proceed with upload (add your file upload logic here)
    logging.info(f"Created folder with ID: {date_folder_id}")

def main(
    start_date, 
    end_date, 
    num_files_to_load, 
    batch_size, 
    strict_otm, 
    min_trade_value, 
    expiration_days_out,
    number_of_bins, 
    max_clusters,
    itm_threshold, 
    short_term_days_out, 
    medium_term_days_out, 
    long_term_days_out, 
    atr_max, 
    days_to_include, 
    k_value
):
    # Capture and print start time
    start_time = time.time()
    print(f"!{FILE_NAME}! Start time: {start_time:.2f} seconds")

    # Run raw_data first (sequential)
    print("Starting raw_data execution...")
    run_raw_data(start_date, end_date, num_files_to_load, batch_size)
    print("Completed raw_data execution.")

    # Run run_unusual_baselining first (sequential)
    print("Starting run_unusual_baselining execution...")
    run_unusual_baselining(strict_otm, min_trade_value, expiration_days_out,number_of_bins, max_clusters,itm_threshold)
    print("Completed run_unusual_baselining execution.")

    '''
    # Run run_put_call_anomalies first (sequential)
    print("Starting run_put_call_anomalies execution...")
    run_put_call_anomalies(min_trade_value, short_term_days_out, medium_term_days_out, long_term_days_out, atr_max, days_to_include, k_value)
    print("Completed run_put_call_anomalies execution.")
    '''
    '''
    # List of subsequent applications to run in parallel
    parallel_tasks = [
        run_unusual_baselining,
        # Add future applications here, e.g., run_other_app
    ]

    # Run subsequent tasks in parallel
    if parallel_tasks:
        processes = []
        for task in parallel_tasks:
            p = multiprocessing.Process(target=task)
            processes.append(p)
            p.start()
            print(f"Started {task.__name__} in parallel.")

        # Wait for all parallel tasks to complete
        for p in processes:
            p.join()
        print("All parallel tasks completed.")
    '''

    # push results to GitHub
    print("Starting push_to_github execution...")
    push_to_github()
    print("Completed push_to_github execution.")

    # push results to Google Drive
    # push_to_drive()

    # Print execution time
    end_time = time.time()
    print(f"!{FILE_NAME}! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!{FILE_NAME}! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser(description="Run 'put_call_anomalies' scripts with specified parameters")
    parser.add_argument("--start-date", type=str, default=raw_config.START_DATE, help="Start date (YYYY-MM-DD), defaults to config.START_DATE")
    parser.add_argument("--end-date", type=str, default=raw_config.END_DATE, help="End date (YYYY-MM-DD), defaults to today")
    parser.add_argument("--num-files-to-load", type=int, default=raw_config.NUM_FILES_TO_PROCESS, help="Number of files to load, defaults to config.NUM_FILES_TO_PROCESS")
    parser.add_argument("--batch-size", type=int, default=raw_config.BATCH_SIZE)

    parser.add_argument("--strict-otm", type=bool_type, default=ub_config.STRICT_OTM, help="Use strict OTM range")
    parser.add_argument("--min-trade-value", type=float, default=ub_config.MIN_TRADE_VALUE, help="Minimum trade value")
    parser.add_argument("--expiration-days-out", type=int, default=ub_config.EXPIRATION_DAYS_OUT, help="Expiration days out")
    parser.add_argument("--number-of-bins", type=int, default=ub_config.NUMBER_OF_BINS, help="Number of bins")
    parser.add_argument("--max-clusters", type=int, default=ub_config.MAX_CLUSTERS, help="Max k for clustering")
    parser.add_argument("--itm-threshold", type=float, default=ub_config.ITM_THRESHOLD, help="ITM threshold")

    parser.add_argument("--short-term-days-out", type=int, default=pca_config.SHORT_TERM_DAYS_OUT, help="Short term days out")
    parser.add_argument("--medium-term-days-out", type=int, default=pca_config.MEDIUM_TERM_DAYS_OUT, help="Medium term days out")
    parser.add_argument("--long-term-days-out", type=int, default=pca_config.LONG_TERM_DAYS_OUT, help="Long term days out")
    parser.add_argument("--atr-max", type=int, default=pca_config.ATR_MAX, help="ATR max out")
    parser.add_argument("--days-to-include", type=int, default=pca_config.DAYS_TO_INCLUDE, help="Days to consider for analysis")
    parser.add_argument("--k-value", type=float, default=pca_config.MAD_K, help="k value for Median Absolute Deviation (MAD)")

    args = parser.parse_args()

    end_date = args.end_date if args.end_date is not None else datetime.now().strftime("%Y-%m-%d")

    main(
        args.start_date, 
        end_date, 
        args.num_files_to_load, 
        args.batch_size, 
        args.strict_otm, 
        args.min_trade_value, 
        args.expiration_days_out,
        args.number_of_bins, 
        args.max_clusters,
        args.itm_threshold,
        args.short_term_days_out, 
        args.medium_term_days_out, 
        args.long_term_days_out, 
        args.atr_max, 
        args.days_to_include, 
        args.k_value
    )