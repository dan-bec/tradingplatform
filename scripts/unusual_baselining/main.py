import argparse
import subprocess
import os
from datetime import datetime
import time
import config as config
import upload_to_drive as upload_to_drive
import logging
from pathlib import Path

def str_to_bool(value):
    if str(value).lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif str(value).lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError(f"Invalid boolean value: '{value}'")
    
def run_script(script_name, args_list):
    """Helper function to run a script with given arguments."""
    cmd = ["python3", config.APP_DIR / script_name] + args_list
    subprocess.run(cmd, check=True)

def export_settings():
    # Define the output directory and file
    output_dir = config.ITM_PATH
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'settings.txt'

    # Get all settings from config, excluding special attributes
    settings_dict = {k: v for k, v in vars(config).items() if not k.startswith('__')}

    # Define the subset of keys to export
    desired_keys = {'STRICT_OTM', 'MIN_TRADE_VALUE', 'TOP_N_TRADES', 'EXPIRATION_DAYS_OUT', 'NUMBER_OF_BINS', ''}

    # Filter the settings to include only the desired keys that exist in config
    subset_dict = {k: settings_dict[k] for k in desired_keys & settings_dict.keys()}

    # Write the subset of settings to the file
    with open(output_file, 'w') as f:
        for key in sorted(subset_dict):
            value = subset_dict[key]
            f.write(f"{key}: {repr(value)}\n")

def push_to_github():
    # Set the repository root (parent of /scripts)
    repo_root = config.REPO_ROOT
    # Add all changes from the repository root
    subprocess.run(["git", "-C", repo_root, "add", "."], check=True)
    # Commit with a timestamped message
    commit_message = f"Update outputs {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    subprocess.run(["git", "-C", repo_root, "commit", "-m", commit_message], check=True)
    # Push to the specified branch (adjust 'main' to your branch name)
    subprocess.run(["git", "-C", repo_root, "push", "origin", "main"], check=True)

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

def main():
    # Capture and print start time
    start_time = time.time()
    print(f"Main Start time: {start_time:.2f} seconds")

    # Define command-line arguments
    parser = argparse.ArgumentParser(description="Run all scripts with specified parameters")
    parser.add_argument("--start-date", type=str, default=config.START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=config.END_DATE, help="End date (YYYY-MM-DD)")
    parser.add_argument("--num-files-to-load", type=int, default=config.NUM_FILES_TO_PROCESS, help="Number of files to load")
    parser.add_argument("--strict-otm", type=str_to_bool, default=config.STRICT_OTM, help="Use strict OTM range")
    parser.add_argument("--min-trade-value", type=float, default=config.MIN_TRADE_VALUE, help="Minimum trade value")
    parser.add_argument("--top-trades", type=int, default=config.TOP_N_TRADES, help="Top trades")
    parser.add_argument("--expiration-days-out", type=int, default=config.EXPIRATION_DAYS_OUT, help="Expiration days out")
    parser.add_argument("--number-of-bins", type=int, default=config.NUMBER_OF_BINS, help="Number of bins")
    parser.add_argument("--max-k", type=int, default=config.MAX_K, help="Max k for clustering")
    parser.add_argument("--itm-threshold", type=float, default=config.ITM_THRESHOLD, help="ITM threshold")

    args = parser.parse_args()

    # Set end_date to today if not provided
    end_date = args.end_date if args.end_date else datetime.now().strftime("%Y-%m-%d")

    # Run scripts in order with appropriate arguments
    run_script("tasks/0_download_data.py", ["--start-date", args.start_date, "--end-date", end_date])

    run_script("tasks/1_raw_data_load.py", [
        "--num-files-to-load", str(args.num_files_to_load)
    ])

    task2_args = [
        "--strict-otm", str(args.strict_otm),
        "--min-trade-value", str(args.min_trade_value),
        "--expiration-days-out", str(args.expiration_days_out),
        "--number-of-bins", str(args.number_of_bins)
    ]

    run_script("tasks/2_prep_data_filtering.py", task2_args)

    task3_args = [
        "--number-of-bins", str(args.number_of_bins),
        "--max-k", str(args.max_k)
    ]

    run_script("tasks/3_per_security_clustering.py", task3_args)

    run_script("tasks/4_optimal_itm_p_value.py", ["--itm-threshold", str(args.itm_threshold)])

    run_script("tasks/5_combined_analysis_and_output.py", ["--itm-threshold", str(args.itm_threshold)])

    export_settings()

    # push results to GitHub
    push_to_github()

    # push results to Google Drive
    # push_to_drive()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"Main Start time: {start_time:.2f} seconds")

    push_to_github()

    # Print execution time
    end_time = time.time()
    print(f"Main End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Main Execution time: {duration:.2f} seconds")