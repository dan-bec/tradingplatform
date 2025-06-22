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

def main(days_to_include):
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    days_to_include_str = str((days_to_include))

    print(f"Building {prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days AS
        WITH _predict_days AS (
            select prediction_date
                ,security
                ,dte_category
                ,dates_considered
                ,day_of_put_trade_value
                ,day_of_call_trade_value
                ,day_of_call_put_ratio
                ,median_ratio
                ,mad
                ,mad_multiplier
                ,lower_bound
                ,upper_bound
            from {prep_schema}.predict_cp_ratio_{days_to_include_str}_days
        )
        , _stock_data AS (
            select security 
                , volume 
                , open 
                , close 
                , high 
                , low 
                , window_start 
                , transactions 
                , data_date 
                , lead(data_date) over (partition by security order by data_date) as one_day_later
                , lead(data_date,2) over (partition by security order by data_date) as two_days_later
                , lead(data_date,3) over (partition by security order by data_date) as three_days_later
                , lead(data_date,4) over (partition by security order by data_date) as four_days_later
            from {raw_schema}.stock_daily_data
        )
        
        select pd.security
            , pd.prediction_date data_date
            , pd.dte_category
            , pd.dates_considered
            , pd.day_of_put_trade_value
            , pd.day_of_call_trade_value
            , pd.day_of_call_put_ratio
            , pd.median_ratio
            , pd.mad
            , pd.mad_multiplier
            , pd.lower_bound
            , pd.upper_bound
            , case 
                when sdt.data_date is null then 0
                when pd.day_of_call_put_ratio > pd.upper_bound then 1
                when pd.day_of_call_put_ratio < pd.lower_bound then -1
                else 0
              end inside_outside_range
            , round((sdt.open - sd.close) / sd.close , 5) as next_day_open_change_pct
            , round((sdt.high - sd.close) / sd.close , 5) as next_day_high_change_pct
            , round((sdt.low - sd.close) / sd.close , 5) as next_day_low_change_pct
            , round((sdt.close - sd.close) / sd.close , 5) as next_day_close_change_pct
            , round((sdtw.open - sd.close) / sd.close , 5) as two_day_open_change_pct
            , round((sdtw.high - sd.close) / sd.close , 5) as two_day_high_change_pct
            , round((sdtw.low - sd.close) / sd.close , 5) as two_day_low_change_pct
            , round((sdtw.close - sd.close) / sd.close , 5) as two_day_close_change_pct
            , round((sdth.open - sd.close) / sd.close , 5) as three_day_open_change_pct
            , round((sdth.high - sd.close) / sd.close , 5) as three_day_high_change_pct
            , round((sdth.low - sd.close) / sd.close , 5) as three_day_low_change_pct
            , round((sdth.close - sd.close) / sd.close , 5) as four_day_close_change_pct
            , round((sdf.open - sd.close) / sd.close , 5) as four_day_open_change_pct
            , round((sdf.high - sd.close) / sd.close , 5) as four_day_high_change_pct
            , round((sdf.low - sd.close) / sd.close , 5) as four_day_low_change_pct
            , round((sdf.close - sd.close) / sd.close , 5) as four_day_close_change_pct
        from _predict_days pd
        left join _stock_data sd on sd.data_date = pd.prediction_date and sd.security = pd.security
        left join _stock_data sdt on sdt.data_date = sd.one_day_later and sdt.security = sd.security
        left join _stock_data sdtw on sdtw.data_date = sd.four_days_later and sdtw.security = sd.security
        left join _stock_data sdth on sdth.data_date = sd.four_days_later and sdth.security = sd.security
        left join _stock_data sdf on sdf.data_date = sd.four_days_later and sdf.security = sd.security
        ORDER BY pd.security
            , pd.prediction_date
    """)
    print(f"!!!ROWS IN {prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days").fetchone()[0]) # type: ignore

    # Output {project}_percentiles files and baseline file
    outcomes_ranges_output = Path(f"{prep_dir}/cp_ratio_outcomes_{days_to_include_str}_days.csv")
    con.execute(f"""
        COPY (
            SELECT *
            FROM {prep_schema}.cp_ratio_outcomes_{days_to_include_str}_days
        ) TO '{outcomes_ranges_output}' (HEADER, DELIMITER ',')
    """)
    print(f"Call-Put Ratio outcomes data written to {outcomes_ranges_output}")

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
    args = parser.parse_args()

    main(args.days_to_include)
