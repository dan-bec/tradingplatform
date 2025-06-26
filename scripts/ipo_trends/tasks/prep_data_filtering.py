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

import scripts.ipo_trends.config as config
import time
import duckdb

def bool_type(value):
    try:
        return config.str_to_bool(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
output_dir = config.PREP_OUTPUT_DIR

def main(days_since_ipo):
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")
    
    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    con.execute(f"DROP SCHEMA IF EXISTS {prep_schema} CASCADE;")
    con.execute(f"CREATE SCHEMA {prep_schema};")
    print(f"CREATE OR REPLACE SCHEMA {prep_schema};")

    # Create trades_data table with only the relevant trades
    con.execute(f"""
        CREATE OR REPLACE TABLE {prep_schema}.ipos_first_{days_since_ipo}_days AS
        with _ipo_dates as (
                    select sdd.security, min(sdd.data_date) ipo_date
                    from {raw_schema}.stock_daily_data sdd
                    -- cross join (select min(data_date) ed_date from {raw_schema}.stock_daily_data) ed
                    group by 1
                    having  min(sdd.data_date) > (select min(data_date) ed_date from {raw_schema}.stock_daily_data)
            )
            , _row_nums as (
            
                select sdd.*
                , row_number() over (partition by sdd.security order by sdd.data_date) - 1 as rn
                from _ipo_dates ipo
                join {raw_schema}.stock_daily_data sdd on sdd.security = ipo.security and sdd.data_date >= ipo.ipo_date
            )
            , _max_row_nums as (
            
                select *
                , max(rn) over (partition by security) as max_rn
                from _row_nums
            )

            select mrn.security
            , mrn.volume 
            , mrn.open 
            , mrn.close 
            , mrn.high 
            , mrn.low 
            , mrn.window_start 
            , mrn.transactions 
            , mrn.data_date           
            , mrn.rn
            , si.sector
            , si.industry
            from _max_row_nums mrn
            join {raw_schema}.sector_industry si on mrn.security = si.security
            where 1=1
            and rn <= {days_since_ipo}
            and max_rn >= {days_since_ipo}
            order by mrn.security, mrn.data_date
    """)
    print(f"!!!ROWS IN {prep_schema}.ipos_first_{days_since_ipo}_days!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.ipos_first_{days_since_ipo}_days").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

    # Print execution time
    end_time = time.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-since-ipo", type=int, default = config.DAYS_SINCE_IPO, help="Expiration days out")
    args = parser.parse_args()

    main(args.days_since_ipo)