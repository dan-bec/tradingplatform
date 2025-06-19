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

def main(atr_max):
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")


    print(f"Building {prep_schema}.agg_filtered_options_trades table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.agg_filtered_options_trades AS
        WITH _trade_prep AS (
            SELECT *
            FROM {prep_schema}.filtered_options_trades
        )

        SELECT tp.data_date
            , tp.security
            , tp.sector
            , tp.industry
            , tp.option_type
            , tp.purchase_itm_otm
            , tp.dte_category
            , tp.min_trade_value
            , tp.expiration_days_out
            , tp.atr_multiple_rounded
            , min(tp.expiration) as min_expiration_date
            , max(tp.expiration) as max_expiration_date
            , sum(tp.trade_value) trade_value
            , sum(tp.trade_size) as trade_size
            , count(*) as trade_count
        FROM _trade_prep tp
        WHERE tp.atr_multiple_rounded <= {atr_max}
        GROUP BY 1,2,3,4,5,6,7,8,9,10
        ORDER BY tp.data_date, tp.security
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
    parser.add_argument("--atr-max", type=int, default=config.ATR_MAX, help="ATR max out")
    args = parser.parse_args()

    main(args.atr_max)

    # Print execution time
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")
