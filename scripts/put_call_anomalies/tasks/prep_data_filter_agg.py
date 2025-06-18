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

def main(min_trade_value, short_term_days_out, medium_term_days_out, long_term_days_out):
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
            SELECT min_trade_value, expiration_days_out, MAX(data_date) AS max_data_date
            FROM {prep_schema}.agg_filtered_options_trades
            GROUP BY 1,2
        """).fetchone()
        if current_settings:
            current_min_trade_value, current_expiration_days_out, current_max_data_date = current_settings
            raw_max_data_date = con.execute(f"SELECT MAX(data_date) FROM {raw_schema}.all_options_trades_data").fetchone()[0] # type: ignore
            print(f"raw max date: {raw_max_data_date}. prep max date: {current_max_data_date}")
            if (current_min_trade_value == min_trade_value and
                current_expiration_days_out == long_term_days_out_str and
                current_max_data_date == raw_max_data_date):
                print("Settings match and data is up-to-date. Skipping rebuild.")
                rebuild = False
    except duckdb.CatalogException:
        # Table or schema doesn't exist, so proceed with rebuild
        pass

    if rebuild:
        print(f"Building {prep_schema}.agg_filtered_options_trades table")
        con.execute(f"DROP SCHEMA IF EXISTS {prep_schema} CASCADE;")
        con.execute(f"CREATE SCHEMA {prep_schema};")
        print(f"CREATE OR REPLACE SCHEMA {prep_schema};")

        print(f"Building {prep_schema}.agg_filtered_options_trades table")
        # Create trades_data table with only the relevant trades
        con.execute(f"""
            CREATE OR REPLACE TABLE {prep_schema}.agg_filtered_options_trades AS
            WITH _trade_prep AS (
                SELECT atd.data_date
                    , atd.security
                    , atd.option_ticker
                    , si.sector
                    , si.industry
                    , atd.option_type
                    , CASE
                        WHEN (atd.option_type = 'C' AND atd.strike_price > std.high) OR (atd.option_type = 'P' AND atd.strike_price < std.low )
                        THEN 'otm'
                        ELSE 'itm'
                      END as purchase_itm_otm
                    , CASE
                        WHEN atd.expiration - atd.data_date <= {short_term_days_out} THEN 'short_term_expiration_{short_term_days_out_str}'
                        WHEN atd.expiration - atd.data_date <= {medium_term_days_out} THEN 'medium_term_expiration_{medium_term_days_out_str}'
                        WHEN atd.expiration - atd.data_date <= {long_term_days_out} THEN 'long_term_expiration_{long_term_days_out_str}'
                        ELSE (atd.expiration - atd.data_date)::VARCHAR
                      END dte_category
                    , {min_trade_value} as min_trade_value
                    , {long_term_days_out} as expiration_days_out
                    , (atd.trade_value) as trade_value
                    , (atd.size) as trade_size
                FROM {raw_schema}.all_options_trades_data atd
                JOIN {raw_schema}.option_condition_codes occ ON occ.id = atd.conditions
                JOIN {raw_schema}.sector_industry si ON si.security = atd.security
                JOIN {raw_schema}.stock_daily_data std ON std.security = atd.security AND std.data_date = atd.data_date
                WHERE 1=1
                    AND atd.conditions >= 209 -- Filters out Late, Canceled trades
                    AND atd.conditions < 248 -- Filters out after market trading
                    AND atd.expiration > atd.data_date -- Options Purchased before Expiration
                    AND atd.expiration <= atd.data_date + INTERVAL {long_term_days_out}  DAYS -- Options Expiring in N days
                    AND atd.trade_value > {min_trade_value} -- minmum contract size of N
            )

            , _unique_qualifying_options AS (
                SELECT security,option_ticker,data_date,expiration
                FROM _trade_prep tp
                GROUP BY 1,2,3,4
            )
            , _security_prices AS (
                SELECT uqo.security
                    , uqo.option_ticker
                    , uqo.data_date
                    , uqo.expiration
                    , max(CASE WHEN sdd.data_date > uqo.data_date THEN sdd.high END) as high_during_period
                    , min(CASE WHEN sdd.data_date > uqo.data_date THEN sdd.low  END) as low_during_period
                    , max(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.high END) as high_expiration
                    , min(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.low  END) as low_expiration
                    , min(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.close  END) as close_expiration
                FROM _unique_qualifying_options uqo
                LEFT JOIN {raw_schema}.stock_daily_data sdd ON sdd.security = uqo.security and sdd.data_date > uqo.data_date and sdd.data_date <= uqo.expiration
                GROUP BY 1,2,3,4
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
                , sum(tp.trade_value) trade_value
                , sum(tp.trade_size) as trade_size
                , count(*)
            FROM _trade_prep tp
            GROUP BY 1,2,3,4,5,6,7,8,9
            ORDER BY tp.data_date, tp.security
        """)
        print(f"!!!ROWS IN {prep_schema}.agg_filtered_options_trades!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.agg_filtered_options_trades").fetchone()[0]) # type: ignore
    else:
        print(f"Using existing {prep_schema}.agg_filtered_options_trades table")

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
    args = parser.parse_args()

    main(args.min_trade_value, args.short_term_days_out, args.medium_term_days_out, args.long_term_days_out)

    # Print execution time
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")
