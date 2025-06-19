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

def main(min_trade_value, short_term_days_out, medium_term_days_out, long_term_days_out, atr_max):
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    min_trade_value_str = str((min_trade_value))
    short_term_days_out_str = str((short_term_days_out))
    medium_term_days_out_str = str((medium_term_days_out))
    long_term_days_out_str = str((long_term_days_out))

    # Check if rebuild is necessary
    rebuild = True
    try:
        current_settings = con.execute(f"""
            SELECT min_trade_value, expiration_days_out,  MAX(data_date) AS max_data_date
            FROM {prep_schema}.filtered_options_trades
            GROUP BY 1,2
        """).fetchone()
        if current_settings:
            current_min_trade_value, current_expiration_days_out, current_max_data_date = current_settings
            raw_max_data_date = con.execute(f"SELECT MAX(data_date) FROM {raw_schema}.all_options_trades_data").fetchone()[0] # type: ignore
            if (current_min_trade_value == min_trade_value and
                current_expiration_days_out == long_term_days_out and
                current_max_data_date == raw_max_data_date):
                print("Settings match and data is up-to-date. Skipping rebuild.")
                rebuild = False
    except duckdb.Error as e:
        pass
        print("Table or schema does not exist. Proceeding with rebuild.")

    if rebuild:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {prep_schema};")
        print(f"CREATE SCHEMA IF NOT EXISTS {prep_schema};")

        con.execute(f"""
            CREATE TABLE IF NOT EXISTS {prep_schema}.filtered_options_trades (
                data_date	DATE	,
                security	VARCHAR	,
                option_ticker	VARCHAR	,
                option_condition_name	VARCHAR	,
                sector	VARCHAR	,
                industry	VARCHAR	,
                option_type	VARCHAR	,
                expiration	DATE	,
                purchase_itm_otm	VARCHAR	,
                dte_category	VARCHAR	,
                strike_diff_hl_price	DOUBLE	,
                least_atr	DOUBLE	,
                atr_multiple_raw	DOUBLE	,
                atr_multiple_rounded	DOUBLE	,
                min_trade_value	INTEGER	,
                expiration_days_out	INTEGER	,
                trade_value	DOUBLE	,
                trade_size	INTEGER	
                )
        """)
        print(f"Created {prep_schema}.filtered_options_trades db table")

        print(f"Loading {prep_schema}.filtered_options_trades table")
        # Create trades_data table with only the relevant trades
        con.execute(f"""
            INSERT INTO {prep_schema}.filtered_options_trades
            SELECT atd.data_date
                , atd.security
                , atd.option_ticker
                , occ.name as option_condition_name
                , si.sector
                , si.industry
                , atd.option_type
                , atd.expiration
                , CASE
                    WHEN (atd.option_type = 'C' AND atd.strike_price > std.high) OR (atd.option_type = 'P' AND atd.strike_price < std.low )
                    THEN 'otm'
                    ELSE 'itm'
                    END as purchase_itm_otm
                , CASE
                    WHEN atd.expiration - atd.data_date <= {short_term_days_out} THEN '1. short_term_expiration_{short_term_days_out_str}'
                    WHEN atd.expiration - atd.data_date <= {medium_term_days_out} THEN '2. medium_term_expiration_{medium_term_days_out_str}'
                    WHEN atd.expiration - atd.data_date <= {long_term_days_out} THEN '3. long_term_expiration_{long_term_days_out_str}'
                    ELSE (atd.expiration - atd.data_date)::VARCHAR
                    END dte_category
                , abs(atd.strike_price - case atd.option_type when 'C' then std.high when 'P' then std.low end) as strike_diff_hl_price
                , least(sa.classic_atr,sa.wilder_smoothed_atr) as least_atr
                , strike_diff_hl_price / nullif(least_atr,0) as atr_multiple_raw
                , round(atr_multiple_raw * 2) / 2 as atr_multiple_rounded
                , {min_trade_value} as min_trade_value
                , {long_term_days_out} as expiration_days_out
                , (atd.trade_value) as trade_value
                , (atd.size) as trade_size
            FROM {raw_schema}.all_options_trades_data atd
            JOIN {raw_schema}.option_condition_codes occ ON occ.id = atd.conditions
            JOIN {raw_schema}.sector_industry si ON si.security = atd.security
            JOIN {raw_schema}.stock_daily_data std ON std.security = atd.security AND std.data_date = atd.data_date
            JOIN {raw_schema}.security_atr sa ON sa.security = atd.security and sa.data_date = atd.data_date
            WHERE 1=1
                AND atd.conditions >= 209 -- Filters out Late, Canceled trades
                AND atd.conditions < 248 -- Filters out after market trading
                AND atd.expiration > atd.data_date -- Options Purchased before Expiration
                AND atd.expiration <= atd.data_date + INTERVAL {long_term_days_out}  DAYS -- Options Expiring in N days
                AND atd.trade_value > {min_trade_value} -- minmum contract size of N
                AND atd.data_date > '{latest_prep_date}'::date
    """)
    print(f"!!!ROWS IN {prep_schema}.filtered_options_trades!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.filtered_options_trades").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

if __name__ == "__main__":
    # Capture and print start time
    start_time = time.time()
    print(f"Start time: {start_time:.2f} seconds")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-trade-value", type=float, default=config.MIN_TRADE_VALUE, help="Minimum trade value")
    parser.add_argument("--short-term-days-out", type=int, default=config.SHORT_TERM_DAYS_OUT, help="Short term days out")
    parser.add_argument("--medium-term-days-out", type=int, default=config.MEDIUM_TERM_DAYS_OUT, help="Medium term days out")
    parser.add_argument("--long-term-days-out", type=int, default=config.LONG_TERM_DAYS_OUT, help="Long term days out")
    parser.add_argument("--atr-max", type=int, default=config.LONG_TERM_DAYS_OUT, help="ATR max out")
    args = parser.parse_args()

    main(args.min_trade_value, args.short_term_days_out, args.medium_term_days_out, args.long_term_days_out, args.atr_max)

    # Print execution time
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")
