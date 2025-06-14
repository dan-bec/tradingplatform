import argparse
import subprocess
import os
from datetime import datetime
import time
import config

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

def str_to_bool(value):
    if str(value).lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif str(value).lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError(f"Invalid boolean value: '{value}'")
    
def run_script(script_name, args_list):
    """Helper function to run a script with given arguments."""
    cmd = ["python3", config.SCRIPT_DIR / script_name] + args_list
    subprocess.run(cmd, check=True)

def push_to_github():
    # Commit and push to GitHub
    repo_root = os.path.dirname(os.path.abspath(__file__))  # /scripts folder
    os.chdir(repo_root)  # Stay in /scripts for relative paths to work
    subprocess.run(["git", "add", "../*"], check=True)  # Add changes in repo root
    commit_message = f"Update outputs {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    subprocess.run(["git", "commit", "-m", commit_message], check=True)
    subprocess.run(["git", "push"], check=True)    

def main():
    # Capture and print start time
    start_time = time.time()
    print(f"RUN_ALL Start time: {start_time:.2f} seconds")

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
    run_script("download_data.py", ["--start-date", args.start_date, "--end-date", end_date])

    run_script("v3_1_raw_data_load.py", [
        "--num-files-to-load", str(args.num_files_to_load)
    ])

    v3_2_args = [
        "--strict-otm", str(args.strict_otm),
        "--min-trade-value", str(args.min_trade_value),
        "--top-trades", str(args.top_trades),
        "--expiration-days-out", str(args.expiration_days_out),
        "--number-of-bins", str(args.number_of_bins)
    ]

    run_script("v3_2_option_baselining.py", v3_2_args)

    v3_3_args = [
        "--number-of-bins", str(args.number_of_bins),
        "--max-k", str(args.max_k)
    ]

    run_script("v3_3_per_security_clustering.py", v3_3_args)

    run_script("v3_4_optimal_itm_p_value.py", ["--itm-threshold", str(args.itm_threshold)])

    run_script("v3_5_combined_analysis_and_output.py", ["--itm-threshold", str(args.itm_threshold)])

    # push_to_github()

    # Print execution time
    end_time = time.time()
    print(f"RUN_ALL End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"RUN_ALL Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    push_to_github()


