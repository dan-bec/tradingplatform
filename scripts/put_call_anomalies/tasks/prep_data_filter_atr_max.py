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

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
prep_dir = config.PREP_OUTPUT_DIR
prep_dir.mkdir(parents=True, exist_ok=True)
number_of_bins = config.NUMBER_OF_BINS

def main(atr_max):
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    print(f"Building {prep_schema}.filtered_options_trades_max_atr_{atr_max} table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.filtered_options_trades_max_atr_{atr_max} AS
        WITH _trade_prep AS (
            SELECT *
            FROM {prep_schema}.filtered_options_trades
            WHERE atr_multiple_rounded <= {atr_max}
        ),
        _vol_prep AS (
            SELECT security
                ,sum(trade_count) as security_trade_count
                , ((ROUND(log10(security_trade_count) * 2) / 2) * 10)::int as trade_volume_bin
            FROM _trade_prep
            group by security
        ),
        _bin_prep AS (
            SELECT  trade_volume_bin
                    , ntile({number_of_bins}) OVER (ORDER BY trade_volume_bin desc) as trade_volume_bin_rank
            FROM _vol_prep
            group by trade_volume_bin
        ),
        _vol_bin_securities AS (
            select vp.security
            from _vol_prep vp
            join _bin_prep bp on vp.trade_volume_bin = bp.trade_volume_bin
            where trade_volume_bin_rank < {number_of_bins}
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
        JOIN _vol_bin_securities vbs on vbs.security = tp.security
        GROUP BY 1,2,3,4,5,6,7,8,9,10
        ORDER BY tp.data_date, tp.security
    """)
    print(f"!!!ROWS IN {prep_schema}.filtered_options_trades_max_atr_{atr_max}!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.filtered_options_trades_max_atr_{atr_max}").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()
    print(f"Closed DuckDB database: {full_db_path}")

    # Print execution time
    end_time = time.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--atr-max", type=int, default=config.ATR_MAX, help="ATR max out")
    args = parser.parse_args()

    main(args.atr_max)