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
import scripts.unusual_baselining.config as config
from scripts.unusual_baselining.tasks.prep_data_filtering import main as prep_main
from scripts.unusual_baselining.tasks.per_security_clustering import main as cluster_main
from scripts.unusual_baselining.tasks.optimal_itm_p_value import main as optimal_main
from scripts.unusual_baselining.tasks.compiled_analysis_and_output import main as combined_main
import logging
from pathlib import Path
import subprocess
import duckdb
import shutil

def bool_type(value):
    try:
        return config.str_to_bool(value)
    except ValueError as e:
        raise ValueError(f"Invalid boolean value: '{value}'")

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

def move_results():
    full_db_path = config.FULL_DB_PATH
    projects_path = config.PROJECTS_PATH
    itm_path = config.ITM_PATH
    itm_threshold_100 = config.ITM_THRESHOLD_100
    prep_schema = config.PREP_SCHEMA

    con = duckdb.connect(full_db_path)
    print(f"Connected to DuckDB database: {full_db_path}")

    latest_data_date_str = result = con.execute(f"SELECT max(data_date) FROM {prep_schema}.filtered_short_term_otm_options_trades").fetchone()[0].strftime("%Y-%m-%d") # type: ignore

    final_path = projects_path / latest_data_date_str
    print(f"Moving files to final desitination: {final_path}")
    shutil.move(itm_path, final_path)
    print(f"Files moved to final desitination: {final_path}")

    if itm_path.exists():
        try:
            shutil.rmtree(itm_path)
            print(f"Deleted folder: {itm_path}")
        except Exception as e:
            print(f"Failed to delete folder: {e}")
    else:
        print(f"Folder does not exist: {itm_path}")

    # Close connection
    con.close()

def main(strict_otm, min_trade_value, expiration_days_out,number_of_bins, max_clusters,itm_threshold):
    # Capture and print start time
    start_time = time.time()
    print(f"!{FILE_NAME}! Start time: {start_time:.2f} seconds")

    print("Running prep_data_filtering...")
    prep_main(strict_otm, min_trade_value, expiration_days_out)
    print("Completed prep_data_filtering.")

    print("Running per_security_clustering...")
    cluster_main(number_of_bins, max_clusters)
    print("Completed per_security_clustering.")

    print("Running optimal_itm_p_value...")
    optimal_main(itm_threshold)
    print("Completed optimal_itm_p_value.")

    print("Running combined_analysis_and_output...")
    combined_main(itm_threshold)
    print("Completed combined_analysis_and_output.")

    print("Running export_sttings...")
    export_settings()
    print("Completed export_sttings.")

    print("Running move_results...")
    move_results()
    print("Completed move_results.")

    # Print execution time
    end_time = time.time()
    print(f"!{FILE_NAME}! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!{FILE_NAME}! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    # Define command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Run 'unusual_baselining' scripts with specified parameters")
    parser.add_argument("--strict-otm", type=bool_type, default=config.STRICT_OTM, help="Use strict OTM range")
    parser.add_argument("--min-trade-value", type=float, default=config.MIN_TRADE_VALUE, help="Minimum trade value")
    parser.add_argument("--expiration-days-out", type=int, default=config.EXPIRATION_DAYS_OUT, help="Expiration days out")
    parser.add_argument("--number-of-bins", type=int, default=config.NUMBER_OF_BINS, help="Number of bins")
    parser.add_argument("--max-clusters", type=int, default=config.MAX_CLUSTERS, help="Max k for clustering")
    parser.add_argument("--itm-threshold", type=float, default=config.ITM_THRESHOLD, help="ITM threshold")
    args = parser.parse_args()

    main(args.strict_otm, args.min_trade_value, args.expiration_days_out,args.number_of_bins, args.max_clusters,args.itm_threshold)