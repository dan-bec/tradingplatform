import sys
from pathlib import Path

# Determine the project root dynamically
TASK_SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = TASK_SCRIPT_DIR.parents[2]  

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.put_call_anomalies.config as config
import time
import duckdb

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
output_dir = config.PREP_OUTPUT_DIR

def main(short_term_days_out, medium_term_days_out, long_term_days_out):
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    short_term_days_out_str = str((short_term_days_out))
    medium_term_days_out_str = str((medium_term_days_out))
    long_term_days_out_str = str((long_term_days_out))

    print(f"Building {prep_schema}.predict_ table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.agg_filtered_options_trades AS
        WITH _daily_ratios AS (
            SELECT 
                data_date,
                security,
                dte_category,
                SUM(CASE WHEN option_type = 'P' THEN trade_value ELSE 0 END) AS put_trade_value,
                SUM(CASE WHEN option_type = 'C' THEN trade_value ELSE 0 END) AS call_trade_value
            FROM {prep_schema}.agg_filtered_options_trades
            GROUP BY data_date, security, dte_category
        ),
        _date_numbers AS (
            SELECT
                data_date
                , ROW_NUMBER() OVER (ORDER BY data_date) AS rn
            FROM _daily_ratios
            GROUP BY data_date
        )
        _ratios_with_rn AS (
            SELECT 
                dr.data_date,
                dr.security,
                dr.dte_category,
                dr.put_trade_value / NULLIF(dr.call_trade_value, 0) AS put_call_ratio,
                dn.rn
            FROM _daily_ratios dr
            JOIN _date_numbers dn on dr.data_date = dn.data_date
        ),
        prediction_days AS (
            SELECT 
                p.data_date AS prediction_date,
                p.security,
                p.dte_category,
                p.rn AS prediction_rn,
                r.put_call_ratio
            FROM ratios_with_rn p
            JOIN ratios_with_rn r 
                ON p.security = r.security 
                AND p.dte_category = r.dte_category 
                AND r.rn BETWEEN p.rn - 30 AND p.rn - 1
            WHERE p.rn >= 31
        )
        SELECT 
            prediction_date,
            security,
            dte_category,
            percentile_cont(0.05) WITHIN GROUP (ORDER BY put_call_ratio) AS lower_bound,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY put_call_ratio) AS upper_bound
        FROM prediction_days
        GROUP BY prediction_date, security, dte_category
        ORDER BY security, dte_category, prediction_date
    """)
    print(f"!!!ROWS IN {prep_schema}.agg_filtered_options_trades!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.agg_filtered_options_trades").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"Start time: {start_time:.2f} seconds")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--short-term-days-out", type=int, default=config.SHORT_TERM_DAYS_OUT, help="Short term days out")
    parser.add_argument("--medium-term-days-out", type=int, default=config.MEDIUM_TERM_DAYS_OUT, help="Medium term days out")
    parser.add_argument("--long-term-days-out", type=int, default=config.LONG_TERM_DAYS_OUT, help="Long term days out")
    args = parser.parse_args()

    main(args.short_term_days_out, args.medium_term_days_out, args.long_term_days_out)

    # Print execution time
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")
