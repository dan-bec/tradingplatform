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

def main(days_to_include, k_value):
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    days_to_include_str = str((days_to_include))

    print(f"Building {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days AS
        WITH _daily_ratios AS (
            SELECT 
                data_date,
                security,
                dte_category,
                SUM(CASE WHEN option_type = 'C' THEN trade_value ELSE 0 END) AS call_trade_value,
                SUM(CASE WHEN option_type = 'P' THEN trade_value ELSE 0 END) AS put_trade_value
            FROM {prep_schema}.agg_filtered_options_trades
            GROUP BY data_date, security, dte_category
        ),
        _date_numbers AS (
            SELECT
                data_date,
                ROW_NUMBER() OVER (ORDER BY data_date) AS rn
            FROM _daily_ratios
            GROUP BY data_date
        ),
        _ratios_with_rn AS (
            SELECT 
                dr.data_date,
                dr.security,
                dr.dte_category,
                dr.put_trade_value,
                dr.call_trade_value,
                dr.call_trade_value / NULLIF(dr.put_trade_value + dr.call_trade_value, 0) AS call_put_ratio,
                dn.rn
            FROM _daily_ratios dr
            JOIN _date_numbers dn on dr.data_date = dn.data_date
        ),
        prediction_days AS (
            SELECT 
                p.data_date AS prediction_date,
                p.security,
                p.dte_category,
                p.put_trade_value as day_of_put_trade_value,
                p.call_trade_value as day_of_call_trade_value,
                p.call_put_ratio as day_of_call_put_ratio,
                p.rn AS prediction_rn,
                p.rn - r.rn AS delta,
                r.data_date,
                r.call_trade_value,
                r.put_trade_value,
                r.call_put_ratio
            FROM _ratios_with_rn p
            JOIN _ratios_with_rn r 
                ON p.security = r.security 
                AND p.dte_category = r.dte_category 
                AND r.rn BETWEEN p.rn - {days_to_include} AND p.rn - 1
            WHERE p.rn >= ({days_to_include} + 1)
        )

        SELECT *
        FROM prediction_days
        order by security, dte_category, prediction_date, data_date
    """)
    print(f"!!!ROWS IN {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days").fetchone()[0]) # type: ignore


    print(f"Building {prep_schema}.predict_cp_ratio_{days_to_include_str}_days table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.predict_cp_ratio_{days_to_include_str}_days AS
        WITH medians AS (
            SELECT
                prediction_date,
                security,
                dte_category,
                day_of_put_trade_value,
                day_of_call_trade_value, 
                day_of_call_put_ratio,
                median(call_put_ratio) AS median_ratio
            FROM {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days
            GROUP BY 1,2,3,4,5,6
        ),
        details_with_median AS (
            SELECT
                d.prediction_date,
                d.security,
                d.dte_category,
                d.call_put_ratio,
                m.median_ratio
            FROM {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days d
            JOIN medians m 
                ON d.prediction_date = m.prediction_date 
                AND d.security = m.security 
                AND d.dte_category = m.dte_category
        ),
        mad_calc AS (
            SELECT
                prediction_date,
                security,
                dte_category,
                median(abs(call_put_ratio - median_ratio)) AS mad
            FROM details_with_median
            GROUP BY prediction_date, security, dte_category
        ),
        counts AS (
            SELECT
                prediction_date,
                security,
                dte_category,
                count(*) AS dates_considered
            FROM {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days
            GROUP BY prediction_date, security, dte_category
        )
        SELECT
            c.prediction_date,
            c.security,
            c.dte_category,
            c.dates_considered,
            m.day_of_put_trade_value,
            m.day_of_call_trade_value, 
            m.day_of_call_put_ratio,
            m.median_ratio,
            mc.mad,
            m.median_ratio - ({k_value} * mc.mad) AS lower_bound,
            m.median_ratio + ({k_value} * mc.mad) AS upper_bound
        FROM counts c
        JOIN medians m 
            ON c.prediction_date = m.prediction_date 
            AND c.security = m.security 
            AND c.dte_category = m.dte_category
        JOIN mad_calc mc 
            ON c.prediction_date = mc.prediction_date 
            AND c.security = mc.security 
            AND c.dte_category = mc.dte_category
        ORDER BY c.security, c.prediction_date, c.dte_category
    """)
    print(f"!!!ROWS IN {prep_schema}.predict_cp_ratio_{days_to_include_str}_days!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.predict_cp_ratio_{days_to_include_str}_days").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"Start time: {start_time:.2f} seconds")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-to-include", type=int, default=config.DAYS_TO_INCLUDE, help="Long term days out")
    parser.add_argument("--k-value", type=float, default=config.MAD_K, help="k value for Median Absolute Deviation (MAD)")
    args = parser.parse_args()

    main(args.days_to_include, args.k_value)

    # Print execution time
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")
