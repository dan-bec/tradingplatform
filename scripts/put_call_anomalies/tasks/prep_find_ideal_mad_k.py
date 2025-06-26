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
import duckdb
import pandas as pd
import numpy as np

### SETTINGS ###
# Define file paths and parameters
full_db_path = config.FULL_DB_PATH
prep_schema = config.PREP_SCHEMA
prep_dir = config.PREP_OUTPUT_DIR
prep_dir.mkdir(parents=True, exist_ok=True)
days_to_include = config.DAYS_TO_INCLUDE
days_to_include_str = str(days_to_include)
predictive_threshold = config.PREDICTIVE_THRESHOLD

def main():
    # Connect to DuckDB
    con = duckdb.connect(full_db_path)

    # Load data from the DuckDB table
    table_name = f"{prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days"
    query = f"""
        WITH _data_filter AS (
        SELECT security
        FROM {table_name}
        GROUP BY security
        HAVING count(*) > 100
        )

        SELECT t.security, data_date, dte_category, median_ratio, mad,
            day_of_call_put_ratio, next_day_high_change_pct, next_day_low_change_pct
        FROM {table_name} t
        JOIN _data_filter df on t.security = df.security
    """
    df = con.execute(query).fetchdf()

    # Data cleaning: Drop rows with missing values in key columns
    df = df.dropna(subset=['median_ratio', 'mad', 'day_of_call_put_ratio', 
                           'next_day_high_change_pct', 'next_day_low_change_pct'])

    # Define weights for DTE categories (higher weight for shorter terms)
    weights = {
        "1": 0,  # Highest weight for short term
        "2": 1,
        "3": 1   # Lowest weight for long term
    }

    # Extract the number from 'dte_category' and map to weight
    df['weight'] = df['dte_category'].apply(lambda x: weights.get(x.split('.')[0], 0))

    # Ensure no unmapped DTE categories
    if df['weight'].isna().any():
        raise ValueError("Some dte_category values do not have assigned weights.")

    # Define range of k values to test (from 0.5 to 5.0 with step 0.1)
    k_values = np.arange(0.5, 5.1, 0.1)

    # Define range of change thresholds to test (from 0 to 0.2 with step 0.01)
    change_threshold_values = np.arange(0, 0.21, 0.01)

    # Group by security
    grouped = df.groupby('security')

    # Store results where conditions are met for each security
    security_results = {}

    for security, group in grouped:
        # Check if there are enough data points (assuming 200 dates per security)
        if len(group) < 100:  # Minimum threshold for reliability
            print(f"Skipping {security}: insufficient data ({len(group)} rows)")
            continue
        
        results = []
        for ct in change_threshold_values:
            for k in k_values:
                # Calculate upper and lower bounds
                upper_bound = group['median_ratio'] + (k * group['mad']) # type: ignore
                lower_bound = group['median_ratio'] - (k * group['mad']) # type: ignore
                
                # Identify when call-put ratio is outside the bounds
                above_upper = group['day_of_call_put_ratio'] > upper_bound
                below_lower = group['day_of_call_put_ratio'] < lower_bound
                
                # Check prediction success
                upper_success = above_upper & (group['next_day_high_change_pct'] > ct)
                lower_success = below_lower & (group['next_day_low_change_pct'] < -ct)
                
                # Calculate weighted sums
                weight_above_upper = group['weight'] * above_upper
                weight_upper_success = group['weight'] * upper_success
                weight_below_lower = group['weight'] * below_lower
                weight_lower_success = group['weight'] * lower_success
                
                # Compute success rates, handling cases with no occurrences
                total_weight_above = weight_above_upper.sum()
                total_weight_below = weight_below_lower.sum()
                
                upper_success_rate = (weight_upper_success.sum() / total_weight_above 
                                    if total_weight_above > 0 else 0)
                lower_success_rate = (weight_lower_success.sum() / total_weight_below 
                                    if total_weight_below > 0 else 0)
                
                # Check if both conditions meet the predictive threshold
                if upper_success_rate >= predictive_threshold and lower_success_rate >= predictive_threshold:
                    results.append({
                        'ct': ct,
                        'k': k,
                        'upper_success_rate': upper_success_rate,
                        'lower_success_rate': lower_success_rate,
                        'total_weight_above': total_weight_above,
                        'total_weight_below': total_weight_below
                    })
        
        if results:
            security_results[security] = pd.DataFrame(results)

    # Identify securities with at least one result where ct > 0
    securities_with_ct_gt_0 = [security for security, df in security_results.items() if (df['ct'] > 0).any()]

    # Check if there are any such securities and print accordingly
    if securities_with_ct_gt_0:
        print("Securities with predictive power for ct > 0 found:")
        for security in securities_with_ct_gt_0:
            results_df = security_results[security]  # Fixed: Use security_results instead of securities_with_ct_gt_0
            print(f"\nSecurity: {security} ({len(grouped.get_group(security))} dates)")
            print(results_df.to_string(index=False))
    else:
        print("No securities found where call-put ratio has predictive power for ct > 0.")

    # Insert results into DuckDB table
    if securities_with_ct_gt_0:
        dfs = []
        for security in securities_with_ct_gt_0:  # Fixed: Correct iteration over list
            df = security_results[security]       # Fixed: Fetch DataFrame from security_results
            df['security'] = security
            dfs.append(df)
        combined_df = pd.concat(dfs, ignore_index=True)
    else:
        combined_df = pd.DataFrame(columns=['security', 'ct', 'k', 'upper_success_rate', 
                                           'lower_success_rate', 'total_weight_above', 
                                           'total_weight_below'])

    combined_df = combined_df.sort_values(by=['ct', 'k'], ascending=[False, True])
    con.register("temp_df", combined_df)
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.cp_ratio_mad_k_testing AS
        SELECT * FROM temp_df
    """)
    con.unregister("temp_df")
    print(f"Inserted {len(combined_df)} rows into {prep_schema}.cp_ratio_mad_k_testing")

    # Close the database connection
    con.close()

if __name__ == "__main__":
    main()