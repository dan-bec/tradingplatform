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
import scripts.ipo_trends.config as config
from scripts.ipo_trends.tasks.prep_data_filtering import main as prep_main
from scripts.ipo_trends.tasks.segment_charting import main as charting_main
from scripts.ipo_trends.tasks.compiled_analysis_and_output import main as combined_main
import logging
from pathlib import Path
import duckdb
import os
import shutil

def bool_type(value):
    try:
        return config.str_to_bool(value)
    except ValueError as e:
        raise ValueError(f"Invalid boolean value: '{value}'")

def export_settings():
    # Define the output directory and file
    output_dir = config.IPO_PATH
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'settings.txt'

    # Get all settings from config, excluding special attributes
    settings_dict = {k: v for k, v in vars(config).items() if not k.startswith('__')}

    # Define the subset of keys to export
    desired_keys = {'DAYS_SINCE_IPO'}

    # Filter the settings to include only the desired keys that exist in config
    subset_dict = {k: settings_dict[k] for k in desired_keys & settings_dict.keys()}

    # Write the subset of settings to the file
    with open(output_file, 'w') as f:
        for key in sorted(subset_dict):
            value = subset_dict[key]
            f.write(f"{key}: {repr(value)}\n")

def main(days_since_ipo):
    # Capture and print start time
    start_time = time.time()
    print(f"!{FILE_NAME}! Start time: {start_time:.2f} seconds")

    print("Running prep_data_filtering...")
    prep_main(days_since_ipo)
    print("Completed prep_data_filtering.")

    print("Running per_security_clustering...")
    charting_main(days_since_ipo)
    print("Completed per_security_clustering.")

    print("Running export_sttings...")
    export_settings()
    print("Completed export_sttings.")

    # Print execution time
    end_time = time.time()
    print(f"!{FILE_NAME}! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!{FILE_NAME}! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    # Define command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Run 'ipo_trends' scripts with specified parameters")
    parser.add_argument("--days-since-ipo", type=int, default=config.DAYS_SINCE_IPO, help="Number of days since IPO")
    args = parser.parse_args()

    main(args.days_since_ipo)