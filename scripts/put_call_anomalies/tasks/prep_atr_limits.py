import sys
from pathlib import Path

# Determine the project root dynamically
TASK_SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = TASK_SCRIPT_DIR.parents[2]  

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.put_call_anomalies.config as config
from datetime import datetime, timedelta
import time
import duckdb

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
output_dir = config.PREP_OUTPUT_DIR
latest_prep_date = datetime.strptime(config.latest_db_date(), "%Y-%m-%d")

def main(days_to_include):
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    days_to_include_str = str((days_to_include))

    print(f"Building {prep_schema}.confirm_atr_ranges_{days_to_include_str}_days table")
    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.confirm_atr_ranges_{days_to_include_str}_days AS
        with _data_prep AS (
            select security,data_date,dte_category, atr_multiple_rounded, min(expiration) min_exp, max(expiration) max_exp
            , count(*) cnt
            , sum(trade_value) sum_value
            from {prep_schema}.filtered_options_trades
            where data_date >= '{latest_prep_date}'::date - INTERVAL {days_to_include} DAYS
            group by 1,2,3,4
        ) ,
        _agg_pcts AS (
            select *
            , sum(sum_value) OVER (PARTITION BY data_date,dte_category ORDER BY atr_multiple_rounded ) as sum_value_dt_category
            , sum(sum_value) OVER (PARTITION BY data_date,dte_category ) as tot_sum_value_dt_category
            , sum_value_dt_category / tot_sum_value_dt_category as val_pct_total
            , sum(cnt) OVER (PARTITION BY data_date,dte_category ORDER BY atr_multiple_rounded ) as count_dt_category
            , sum(cnt) OVER (PARTITION BY data_date,dte_category  ) as tot_count_dt_category
            , count_dt_category / tot_count_dt_category as cnt_pct_total
            from _data_prep
        ),
        _filter_aggs AS (
            select security, data_date, dte_category
            , min(atr_multiple_rounded) FILTER (val_pct_total >= .75) as atr_val_p75
            , min(atr_multiple_rounded) FILTER (val_pct_total >= .80) as atr_val_p80
            , min(atr_multiple_rounded) FILTER (val_pct_total >= .85) as atr_val_p85
            , min(atr_multiple_rounded) FILTER (val_pct_total >= .90) as atr_val_p90
            , min(atr_multiple_rounded) FILTER (val_pct_total >= .95) as atr_val_p95
            , min(atr_multiple_rounded) FILTER (cnt_pct_total >= .75) as atr_cnt_p75
            , min(atr_multiple_rounded) FILTER (cnt_pct_total >= .80) as atr_cnt_p80
            , min(atr_multiple_rounded) FILTER (cnt_pct_total >= .85) as atr_cnt_p85
            , min(atr_multiple_rounded) FILTER (cnt_pct_total >= .90) as atr_cnt_p90
            , min(atr_multiple_rounded) FILTER (cnt_pct_total >= .95) as atr_cnt_p95
            from _agg_pcts
            group by 1,2,3
        )

        select dte_category
        , median(atr_val_p75) med_atr_val_p75
        , stddev(atr_val_p75) std_atr_val_p75
        , median(atr_val_p80) med_atr_val_p80
        , stddev(atr_val_p80) std_atr_val_p80
        , median(atr_val_p85) med_atr_val_p85
        , stddev(atr_val_p85) std_atr_val_p85
        , median(atr_val_p90) med_atr_val_p90
        , stddev(atr_val_p90) std_atr_val_p90
        , median(atr_val_p95) med_atr_val_p95
        , stddev(atr_val_p95) std_atr_val_p95
        , median(atr_cnt_p75) med_atr_cnt_p75
        , stddev(atr_cnt_p75) std_atr_cnt_p75
        , median(atr_cnt_p80) med_atr_cnt_p80
        , stddev(atr_cnt_p80) std_atr_cnt_p80
        , median(atr_cnt_p85) med_atr_cnt_p85
        , stddev(atr_cnt_p85) std_atr_cnt_p85
        , median(atr_cnt_p90) med_atr_cnt_p90
        , stddev(atr_cnt_p90) std_atr_cnt_p90
        , median(atr_cnt_p95) med_atr_cnt_p95
        , stddev(atr_cnt_p95) std_atr_cnt_p95
        from _filter_aggs
        group by 1
        order by 1
    """)
    print(f"!!!ROWS IN {prep_schema}.confirm_atr_ranges_{days_to_include_str}_days!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.confirm_atr_ranges_{days_to_include_str}_days").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"Start time: {start_time:.2f} seconds")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-to-include", type=int, default=config.LONG_TERM_DAYS_OUT, help="Days to consider for analysis")
    parser.add_argument("--k-value", type=float, default=config.MAD_K, help="k value for Median Absolute Deviation (MAD)")
    args = parser.parse_args()

    main(args.days_to_include)

    # Print execution time
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")
