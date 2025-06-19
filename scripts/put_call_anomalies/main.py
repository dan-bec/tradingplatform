import sys
from pathlib import Path

# Determine the project root dynamically
APP_DIR = Path(__file__).parent
REPO_ROOT = APP_DIR.parents[1]  

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
    
from datetime import datetime
import time
import scripts.put_call_anomalies.config as config
from scripts.put_call_anomalies.tasks.prep_data_filtering import main as prep_main
from scripts.put_call_anomalies.tasks.prep_atr_limits import main as atr_limit_main
from scripts.put_call_anomalies.tasks.prep_data_filter_agg import main as prep_agg_main
from scripts.put_call_anomalies.tasks.prep_data_predict_ranges import main as predict_main
import logging
from pathlib import Path
import subprocess

def bool_type(value):
    try:
        return config.str_to_bool(value)
    except ValueError as e:
        raise ValueError(f"Invalid boolean value: '{value}'")

def run_script(script_name, args_list):
    """Helper function to run a script with given arguments."""
    cmd = ["python3", config.APP_DIR / script_name] + args_list
    subprocess.run(cmd, check=True)

def export_settings():
    # Define the output directory and file
    output_dir = config.PCA_PATH
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'settings.txt'

    # Get all settings from config, excluding special attributes
    settings_dict = {k: v for k, v in vars(config).items() if not k.startswith('__')}

    # Define the subset of keys to export
    desired_keys = {'MIN_TRADE_VALUE', 'SHORT_TERM_DAYS_OUT', 'MEDIUM_TERM_DAYS_OUT', 'LONG_TERM_DAYS_OUT', 'ATR_MAX', 'DAYS_TO_INCLUDE', 'MAD_K'}

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
    import argparse
    parser = argparse.ArgumentParser(description="Run 'put_call_anomalies' scripts with specified parameters")
    parser.add_argument("--min-trade-value", type=float, default=config.MIN_TRADE_VALUE, help="Minimum trade value")
    parser.add_argument("--short-term-days-out", type=int, default=config.SHORT_TERM_DAYS_OUT, help="Short term days out")
    parser.add_argument("--medium-term-days-out", type=int, default=config.MEDIUM_TERM_DAYS_OUT, help="Medium term days out")
    parser.add_argument("--long-term-days-out", type=int, default=config.LONG_TERM_DAYS_OUT, help="Long term days out")
    parser.add_argument("--atr-max", type=int, default=config.ATR_MAX, help="ATR max out")
    parser.add_argument("--days-to-include", type=int, default=config.DAYS_TO_INCLUDE, help="Days to consider for analysis")
    parser.add_argument("--k-value", type=float, default=config.MAD_K, help="k value for Median Absolute Deviation (MAD)")

    args = parser.parse_args()

    print("Running prep_data_filtering...")
    prep_main(args.min_trade_value, args.short_term_days_out, args.medium_term_days_out, args.long_term_days_out, args.atr_max)
    print("Completed prep_data_filtering.")

    print("Running per_security_clustering...")
    atr_limit_main(args.days_to_include)
    print("Completed per_security_clustering.")

    print("Running optimal_itm_p_value...")
    prep_agg_main(args.atr_max)
    print("Completed optimal_itm_p_value.")

    print("Running combined_analysis_and_output...")
    predict_main(args.days_to_include, args.k_value)
    print("Completed combined_analysis_and_output.")

    export_settings()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"PUT_CALL_ANOMALIES Start time: {start_time:.2f} seconds")

    main()

    # Print execution time
    end_time = time.time()
    print(f"PUT_CALL_ANOMALIES End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"PUT_CALL_ANOMALIES Execution time: {duration:.2f} seconds")