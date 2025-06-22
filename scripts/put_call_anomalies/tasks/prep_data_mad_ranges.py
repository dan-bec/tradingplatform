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

def main(days_to_include, k_value, atr_max):
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    latest_prep_date = con.execute(f"SELECT max(data_date) FROM {prep_schema}.filtered_options_trades").fetchone()[0].strftime("%Y-%m-%d") # type: ignore
    days_to_include_str = str((days_to_include))

    print(f"Building {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days AS
        WITH RECURSIVE _daily_ratios AS (
            SELECT 
                data_date,
                security,
                dte_category,
                SUM(CASE WHEN option_type = 'C' THEN trade_value ELSE 0 END) AS call_trade_value,
                SUM(CASE WHEN option_type = 'P' THEN trade_value ELSE 0 END) AS put_trade_value,
                ROW_NUMBER() OVER (PARTITION BY security, dte_category ORDER BY data_date DESC) as date_filter
            FROM {prep_schema}.filtered_options_trades_max_atr_{atr_max}
            GROUP BY data_date, security, dte_category

            UNION ALL 

            SELECT data_date + CASE datepart('dayofweek', data_date) WHEN 5 THEN 3 ELSE 1 END as data_date,
                security,
                dte_category,
                NULL as call_trade_value,
                NULL as put_trade_value,
                0 as date_filter
            FROM _daily_ratios
            WHERE date_filter = 1
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
                AND r.rn BETWEEN (p.rn - 1 - {days_to_include}) AND p.rn - 1
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
                count(*) AS dates_considered,
                row_number() OVER (PARTITION BY prediction_date, security, dte_category) as dwm_rn
            FROM {prep_schema}.predict_cp_ratio_details_{days_to_include_str}_days
            GROUP BY prediction_date, security, dte_category
        )

        -- https://en.wikipedia.org/wiki/Median_absolute_deviation
        SELECT
            c.prediction_date,
            c.security,
            c.dte_category,
            c.dates_considered,
            m.median_ratio,
            mc.mad,
            {k_value} as mad_multiplier,
            m.median_ratio - ({k_value} * mc.mad) AS lower_bound,
            m.median_ratio + ({k_value} * mc.mad) AS upper_bound,
            m.day_of_put_trade_value,
            m.day_of_call_trade_value, 
            m.day_of_call_put_ratio
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

    # Output {project}_percentiles files and baseline file
    prediction_ranges_output = Path(f"{prep_dir}/predict_cp_ratio_{days_to_include_str}_days.csv")
    con.execute(f"""
        COPY (
            SELECT *
            FROM {prep_schema}.predict_cp_ratio_{days_to_include_str}_days
        ) TO '{prediction_ranges_output}' (HEADER, DELIMITER ',')
    """)
    print(f"Call-Put Ratio predictions data written to {prediction_ranges_output}")

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
    parser.add_argument("--days-to-include", type=int, default=config.DAYS_TO_INCLUDE, help="Long term days out")
    parser.add_argument("--k-value", type=float, default=config.MAD_K, help="k value for Median Absolute Deviation (MAD)")
    parser.add_argument("--atr-max", type=int, default=config.ATR_MAX, help="ATR max out")
    args = parser.parse_args()

    main(args.days_to_include, args.k_value, args.atr_max)
