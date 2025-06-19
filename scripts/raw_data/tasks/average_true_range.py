import sys
from pathlib import Path

# Determine the project root dynamically
TASK_SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = TASK_SCRIPT_DIR.parents[2]  

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.raw_data.config as config
import time
import duckdb

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA

def main():
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    print(f"Building {raw_schema}.security_atr table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {raw_schema}.security_atr AS
        WITH RECURSIVE _tr_calc AS (
            SELECT
                security,
                data_date,
                high,
                low,
                close,
                LAG(close) OVER (PARTITION BY security ORDER BY data_date) AS prev_close,
                ROW_NUMBER() OVER (PARTITION BY security ORDER BY data_date) AS row_num
            FROM raw_data.stock_daily_data
            ),
        _atr_calc AS (
            SELECT
                security,
                data_date,
                row_num,
                CASE
                    WHEN prev_close IS NULL THEN high - low
                    ELSE GREATEST(high - low, ABS(high - prev_close), ABS(low - prev_close))
                END AS true_range
            FROM _tr_calc
            ),
        _classic_atr AS (
            SELECT
                security,
                data_date,
                true_range,
                row_num,
                AVG(true_range) OVER (
                    PARTITION BY security
                    ORDER BY data_date
                    ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
                ) AS atr
            FROM _atr_calc),
        _recursive_smoothed AS (
            -- Anchor: First row for each security
            SELECT
                security,
                data_date,
                true_range AS smoothed_value,
                row_num
            FROM _atr_calc
            WHERE row_num = 1

            UNION ALL

            -- Recursive: Subsequent rows
            SELECT
                o.security,
                o.data_date,
                (0.0714 * o.true_range) + (0.9286 * r.smoothed_value) AS smoothed_value,
                o.row_num
            FROM _atr_calc o
            JOIN _recursive_smoothed r ON o.security = r.security AND o.row_num = r.row_num + 1
            )

        SELECT
            ca.security,
            ca.data_date,
            ca.true_range,
            ca.atr as classic_atr,
            rs.smoothed_value AS wilder_smoothed_atr
        FROM _classic_atr ca
        JOIN _recursive_smoothed rs on ca.security = rs.security and ca.data_date = rs.data_date
        WHERE ca.row_num >= 14
        ORDER BY ca.security, ca.data_date
    """)
    print(f"!!!ROWS IN {raw_schema}.security_atr!!!:", con.execute(f"SELECT COUNT(*) FROM {raw_schema}.security_atr").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"ATR Start time: {start_time:.2f} seconds")

    import argparse
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    main()

    # Print execution time
    end_time = time.time()
    print(f"ATR End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"ATR Execution time: {duration:.2f} seconds")
