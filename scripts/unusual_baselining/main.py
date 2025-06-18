import argparse
from datetime import datetime
import time
import config as config
from tasks.prep_data_filtering import main as prep_main
from tasks.per_security_clustering import main as cluster_main
from tasks.optimal_itm_p_value import main as optimal_main
from tasks.compiled_analysis_and_output import main as combined_main
import upload_to_drive as upload_to_drive
import logging
from pathlib import Path
import subprocess

def bool_type(value):
    try:
        return config.str_to_bool(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))

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

def main():
    # Capture and print start time
    start_time = time.time()
    print(f"Main Start time: {start_time:.2f} seconds")

    # Define command-line arguments
    parser = argparse.ArgumentParser(description="Run 'unusual_baselining' scripts with specified parameters")
    parser.add_argument("--strict-otm", type=bool_type, default=config.STRICT_OTM, help="Use strict OTM range")
    parser.add_argument("--min-trade-value", type=float, default=config.MIN_TRADE_VALUE, help="Minimum trade value")
    parser.add_argument("--expiration-days-out", type=int, default=config.EXPIRATION_DAYS_OUT, help="Expiration days out")
    parser.add_argument("--number-of-bins", type=int, default=config.NUMBER_OF_BINS, help="Number of bins")
    parser.add_argument("--max-k", type=int, default=config.MAX_K, help="Max k for clustering")
    parser.add_argument("--itm-threshold", type=float, default=config.ITM_THRESHOLD, help="ITM threshold")

    args = parser.parse_args()

    print("Running prep_data_filtering...")
    prep_main(args.strict_otm, args.min_trade_value, args.expiration_days_out)
    print("Completed prep_data_filtering.")

    print("Running per_security_clustering...")
    cluster_main(args.number_of_bins, args.max_k)
    print("Completed per_security_clustering.")

    print("Running optimal_itm_p_value...")
    optimal_main(args.itm_threshold)
    print("Completed optimal_itm_p_value.")

    print("Running combined_analysis_and_output...")
    combined_main(args.itm_threshold)
    print("Completed combined_analysis_and_output.")

    export_settings()

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