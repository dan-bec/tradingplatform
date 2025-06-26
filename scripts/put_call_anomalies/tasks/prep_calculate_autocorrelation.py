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
from statsmodels.tsa.stattools import acf
import os

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
prep_dir = config.PREP_OUTPUT_DIR
prep_dir.mkdir(parents=True, exist_ok=True)
days_to_include = config.DAYS_TO_INCLUDE
days_to_include_str = str(days_to_include)
predictive_threshold = config.PREDICTIVE_THRESHOLD
atr_max = config.ATR_MAX

def main():
    # Connect to DuckDB
    con = duckdb.connect(full_db_path)

    # Define the table name (replace with your schema and days value)
    table_name = f"{prep_schema}.filtered_options_trades_max_atr_{atr_max}"

    # Set parameters
    min_obs = 20  # Minimum number of observations required
    nlags = 21    # Number of lags for ACF

    # Get all unique combinations of security and dte_category
    combinations = con.execute(f"SELECT DISTINCT security, dte_category FROM {table_name}").fetchall()
    print(f"Total combinations: {len(combinations)}")

    # Drop and create the acf_results table
    con.execute(f"DROP TABLE IF EXISTS {prep_schema}.acf_results_{days_to_include_str}_days")
    con.execute(f"""
    CREATE TABLE {prep_schema}.acf_results_{days_to_include_str}_days (
        security VARCHAR,
        dte_category VARCHAR,
        lag INTEGER,
        acf_value DOUBLE,
        n INTEGER,
        significance_threshold DOUBLE
    )
    """)

    for security, dte_category in combinations:
        print(f"Processing {security}, {dte_category}")
        
        # Extract time series data for the combination
        query = f"""
        SELECT 
                data_date,
                SUM(CASE WHEN option_type = 'C' THEN trade_value ELSE 0 END) / sum(trade_value) as cp_ratio
            FROM {table_name}
        WHERE security = ? AND dte_category = ?
        GROUP BY data_date
        ORDER BY data_date ASC
        """
        df = con.execute(query, [security, dte_category]).fetchdf()
        
        if len(df) < min_obs:
            print(f"Skipping {security}, {dte_category}: only {len(df)} observations")
            continue
        
        # Check for sufficient non-NaN values in cp_ratio
        valid_observations = df['cp_ratio'].dropna().shape[0]
        if valid_observations < 2:
            print(f"Skipping {security}, {dte_category}: Fewer than 2 non-NaN values in cp_ratio")
            continue
        
        try:
            # Compute ACF for the cp_ratio time series
            acf_values = acf(df['cp_ratio'], nlags=nlags, fft=False)
            
            # Check if acf_values has the expected length
            if len(acf_values) != nlags + 1:
                print(f"Skipping {security}, {dte_category}: acf_values length {len(acf_values)} != {nlags + 1}")
                continue
            
            # Compute significance threshold
            threshold = 2 / np.sqrt(len(df))
            
            # Create DataFrame for CSV output
            acf_df = pd.DataFrame({
                'lag': range(0, nlags + 1),
                'acf_value': acf_values,
                'n': [len(df)] * (nlags + 1),
                'significance_threshold': [threshold] * (nlags + 1)
            })
            
            # Save to CSV
            file_name = f"acf_{security}_{dte_category}.csv".replace('/', '_').replace('\\', '_')
            acf_df.to_csv(os.path.join(prep_dir, file_name), index=False)
            
            # Prepare rows for DuckDB insertion
            rows_to_insert = [(security, dte_category, lag, acf_val, len(df), threshold) 
                              for lag, acf_val in enumerate(acf_values)]
            
            # Insert into DuckDB table
            con.executemany(f"INSERT INTO {prep_schema}.acf_results_{days_to_include_str}_days VALUES (?, ?, ?, ?, ?, ?)", rows_to_insert)
            
            print(f"Completed {security}, {dte_category}")
        
        except ValueError as e:
            print(f"Error computing ACF for {security}, {dte_category}: {e}")
            continue

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