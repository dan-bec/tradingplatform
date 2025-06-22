import sys
from pathlib import Path

# Determine the project root dynamically
FILE_DIR = Path(__file__)
TASK_SCRIPT_DIR = FILE_DIR.parent
REPO_ROOT = TASK_SCRIPT_DIR.parents[2]  
FILE_NAME = FILE_DIR.relative_to(REPO_ROOT)

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.put_call_anomalies.config as config
import time
import duckdb
import pandas as pd
import numpy as np

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
prep_dir = config.PREP_OUTPUT_DIR
prep_dir.mkdir(parents=True, exist_ok=True)
days_to_include = config.DAYS_TO_INCLUDE
days_to_include_str = str((days_to_include))
predictive_threshold = config.PREDICTIVE_THRESHOLD

def main():
    # Connect to DuckDB
    con = duckdb.connect(full_db_path)

    # Load data from the DuckDB table
    table_name = f"{prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days"
    query = f"""
        SELECT security, data_date, dte_category, median_ratio, mad,
            day_of_call_put_ratio, four_day_high_change_pct, four_day_low_change_pct
        FROM {table_name}
    """
    df = con.execute(query).fetchdf()

    # Data cleaning: Drop rows with missing values in key columns
    df = df.dropna(subset=['median_ratio', 'mad', 'day_of_call_put_ratio', 
                        'four_day_high_change_pct', 'four_day_low_change_pct'])

    # Define weights for DTE categories (higher weight for shorter terms)
    weights = {
        "1": 1,  # Highest weight for short term
        "2": 0,
        "3": 0   # Lowest weight for long term
    }

    # Extract the number from 'dte_category' and map to weight
    df['weight'] = df['dte_category'].apply(lambda x: weights.get(x.split('.')[0], 0))

    # Ensure no unmapped DTE categories
    if df['weight'].isna().any():
        raise ValueError("Some dte_category values do not have assigned weights.")

    # Define range of k values to test (from 0 to 0.2 with step 0.01)
    change_threshold_values = np.arange(0, 0.205, 0.005)

    # Define range of k values to test (from 0.5 to 5.0 with step 0.1)
    k_values = np.arange(0.5, 5.1, 0.1)

    # Store results where conditions are met
    results = []

    # Experiment with each k value
    for ct in change_threshold_values:
        for k in k_values:
            # Calculate upper and lower bounds
            upper_bound = df['median_ratio'] + (k * df['mad']) # type: ignore
            lower_bound = df['median_ratio'] - (k * df['mad']) # type: ignore
            
            # Identify when call-put ratio is outside the bounds
            above_upper = df['day_of_call_put_ratio'] > upper_bound
            below_lower = df['day_of_call_put_ratio'] < lower_bound
            
            # Check prediction success
            upper_success = above_upper & (df['four_day_high_change_pct'] > ct)
            lower_success = below_lower & (df['four_day_low_change_pct'] < -ct)
            
            # Calculate weighted sums
            weight_above_upper = df['weight'] * above_upper
            weight_upper_success = df['weight'] * upper_success
            weight_below_lower = df['weight'] * below_lower
            weight_lower_success = df['weight'] * lower_success
            
            # Compute success rates, handling cases with no occurrences
            total_weight_above = weight_above_upper.sum()
            total_weight_below = weight_below_lower.sum()
            
            upper_success_rate = (weight_upper_success.sum() / total_weight_above 
                                if total_weight_above > 0 else 0)
            lower_success_rate = (weight_lower_success.sum() / total_weight_below 
                                if total_weight_below > 0 else 0)
            
            # Check if both conditions meet the 55% threshold
            if upper_success_rate >= predictive_threshold and lower_success_rate >= predictive_threshold:
                results.append({
                    'ct' : ct,
                    'k': k,
                    'upper_success_rate': upper_success_rate,
                    'lower_success_rate': lower_success_rate
                })

    # Convert results list to a pandas DataFrame
    if results:
        results_df = pd.DataFrame(results)
    else:
        results_df = pd.DataFrame(columns=['ct', 'k', 'upper_success_rate', 'lower_success_rate'])

    # Create the table from the DataFrame
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.cp_ratio_mad_k_testing AS
        SELECT *
        FROM results_df
        ORDER BY ct DESC, k
    """)

    # Output results
    if results:
        print("Found k values that satisfy the conditions:")
        for result in results:
            print(f"ct={result['ct']:.2f}: "
                f"k={result['k']:.1f}: "
                f"upper_success_rate={result['upper_success_rate']:.2%}, "
                f"lower_success_rate={result['lower_success_rate']:.2%}")
    else:
        print("No k found that satisfies the conditions. "
            "The call-put ratio may lack predictive power for next-day price movements.")
        

    # Close the database connection
    con.close()

if __name__ == "__main__":
    '''
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-to-include", type=int, default=config.DAYS_TO_INCLUDE, help="Long term days out")
    parser.add_argument("--k-value", type=float, default=config.MAD_K, help="k value for Median Absolute Deviation (MAD)")
    parser.add_argument("--atr-max", type=int, default=config.ATR_MAX, help="ATR max out")
    args = parser.parse_args()
    '''

    main()
