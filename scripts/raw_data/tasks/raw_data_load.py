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

import scripts.raw_data.config as config
import re
from datetime import datetime, date, timedelta
import requests
import time
import duckdb

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
stock_summary_dir = config.STOCK_SUMMARY_DIR
sectors_industries_csv = config.SECTORS_CSV
option_trade_dir = config.OPTION_TRADE_DIR
raw_schema = config.RAW_SCHEMA

# Connect to DuckDB
con = duckdb.connect(str(full_db_path))
print(f"Connected to DuckDB database: {full_db_path}")

# Function to extract static string variables from DataServices.cs
def get_static_string(file_path, var_name):
    """Extracts a static string variable from a C# file."""
    try:
        with open(file_path, 'r') as file:
            content = file.read()
        pattern = rf'public static string {var_name} = "(.*?)";'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        else:
            raise ValueError(f"{var_name} not found in the file")
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {file_path} does not exist")
    except Exception as e:
        raise Exception(f"Error reading {var_name} from {file_path}: {e}")

# Set up API key (kept for condition codes fetching)
dataservices_path = config.DATASERVICES_PATH
API_KEY = get_static_string(dataservices_path, "API_KEY")

def get_files_to_load(src_tbl: str, directory_path: Path, num_files_to_load: int, db_connection: duckdb.DuckDBPyConnection) -> list[str]:
    """
    Retrieves file paths of gzip files in the specified directory that have not yet been loaded into the database.
    """
    # Find all GZIP files in the directory
    all_files = list(directory_path.glob("*.csv.gz"))
    valid_files = []
    for file in all_files:
        try:
            # Extract the date from the file name
            file_date_str = file.name.split('.')[0]  # Gets '2025-05-15' from '2025-05-15.csv.gz'
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d").date()
            valid_files.append((file_date, file))
        except ValueError:
            continue

    if not valid_files:
        print("No valid data files found.")
        return []

    # Sort files by date descending
    valid_files.sort(key=lambda x: x[0], reverse=True)

    # Take the last N files
    last_n_files = valid_files[:num_files_to_load]

    # Get existing dates from the database
    try:
        existing_dates = set(row[0] for row in db_connection.execute(f"SELECT DISTINCT data_date FROM {raw_schema}.{src_tbl}").fetchall())
    except duckdb.CatalogException:
        existing_dates = set()

    # Filter to get only new files
    files_to_load = [(date, file) for date, file in last_n_files if date not in existing_dates]
    file_paths = [str(file) for date, file in files_to_load]
    print(f"!!!TO BE LOADED!!!: {[str(file) for date, file in files_to_load]}")

    # Print latest and earliest dates if files exist
    if files_to_load:
        latest_date = files_to_load[0][0]
        earliest_date = files_to_load[-1][0]
        print(f"Latest date to load: {latest_date}")
        print(f"Earliest date to load: {earliest_date}")
    else:
        print("No new files to load, skipping date identification.")

    return file_paths

### RAW DATA ###
def main(num_files_to_load, batch_size):
    # Capture and print start time
    start_time = time.time()
    print(f"Start time: {start_time:.2f} seconds")

    # Create trades_data table with only the relevant files
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")
    print(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")

    #### CONDITIONS ####

    # Fetch option condition codes from Polygon.io
    condition_codes = []
    url = "https://api.polygon.io/v3/reference/conditions"
    params = {
        "asset_class": "options",
        "order": "asc",
        "limit": 1000,
        "sort": "id",
        "apiKey": API_KEY
    }
    first_request = True
    while url:
        if first_request:
            response = requests.get(url, params=params)
            first_request = False
        else:
            response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            condition_codes.extend(data.get("results", []))
            url = data.get("next_url")
        else:
            print(f"Failed to fetch condition codes: {response.status_code}")
            break

    # Create condition_codes table in DuckDB
    if condition_codes:
        con.execute(f"""
            CREATE OR REPLACE TABLE {raw_schema}.option_condition_codes (
                id INTEGER,
                type VARCHAR,
                name VARCHAR,
                asset_class VARCHAR,
                data_types VARCHAR
            )
        """)
        print(f"CREATE OR REPLACE TABLE {raw_schema}.option_condition_codes")
        for code in condition_codes:
            data_types_str = ",".join(code.get("data_types", []))
            con.execute(
                f"INSERT INTO {raw_schema}.option_condition_codes (id, type, name, asset_class, data_types) VALUES (?, ?, ?, ?, ?)",
                (code.get("id"), code.get("type"), code.get("name"), code.get("asset_class"), data_types_str)
            )
        print("Option condition codes fetched and stored in the database.")
    else:
        print("No condition codes fetched.")

    # Fetch stock condition codes from Polygon.io
    condition_codes = []
    url = "https://api.polygon.io/v3/reference/conditions"
    params = {
        "asset_class": "stocks",
        "order": "asc",
        "limit": 1000,
        "sort": "id",
        "apiKey": API_KEY
    }
    first_request = True
    while url:
        if first_request:
            response = requests.get(url, params=params)
            first_request = False
        else:
            response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            condition_codes.extend(data.get("results", []))
            url = data.get("next_url")
        else:
            print(f"Failed to fetch condition codes: {response.status_code}")
            break

    # Create condition_codes table in DuckDB
    if condition_codes:
        con.execute(f"""
            CREATE OR REPLACE TABLE {raw_schema}.stock_condition_codes (
                id INTEGER,
                type VARCHAR,
                name VARCHAR,
                asset_class VARCHAR,
                data_types VARCHAR
            )
        """)
        print(f"CREATE OR REPLACE TABLE {raw_schema}.stock_condition_codes")
        for code in condition_codes:
            data_types_str = ",".join(code.get("data_types", []))
            con.execute(
                f"INSERT INTO {raw_schema}.stock_condition_codes (id, type, name, asset_class, data_types) VALUES (?, ?, ?, ?, ?)",
                (code.get("id"), code.get("type"), code.get("name"), code.get("asset_class"), data_types_str)
            )
        print("Stock condition codes fetched and stored in the database.")
    else:
        print("No condition codes fetched.")

    #### STOCK SUMMARY DATA ####

    # Create trades_data table with only the relevant files
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {raw_schema}.stock_daily_data (
                security VARCHAR,
                volume BIGINT,
                open DOUBLE,
                close DOUBLE,
                high DOUBLE,
                low DOUBLE,
                window_start BIGINT,
                transactions BIGINT,
                data_date DATE,
                PRIMARY KEY (data_date, security)
            )
    """)
    print(f"Created {raw_schema}.stock_daily_data db table")

    stock_daily_files = get_files_to_load('stock_daily_data',stock_summary_dir, num_files_to_load, con)
    # Load only the new files
    if stock_daily_files:
        total_batches = ((len(stock_daily_files) - 1) // batch_size) + 1
        for i in range(0, len(stock_daily_files), batch_size):
            batch = stock_daily_files[i:i + batch_size]
            print(f"Loading batch {i // batch_size + 1} of {total_batches} for stock_daily_data")
            con.execute(f"""
                INSERT INTO {raw_schema}.stock_daily_data
                SELECT 
                    ticker,
                    volume,
                    open,
                    close,
                    high,
                    low,
                    window_start,
                    transactions,
                    CAST(
                        CASE
                            WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv.gz$', 1) != '' 
                            THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv.gz$', 1)
                            ELSE NULL
                        END AS DATE
                    ) AS data_date
                FROM read_csv_auto({batch}, filename=True, compression='gzip')
            """)
        print(f"Loaded data from {len(stock_daily_files)} new files into {raw_schema}.stock_daily_data")
    else:
        print(f"No new data to load to {raw_schema}.stock_daily_data.")
    print(f"!!!ROWS IN {raw_schema}.stock_daily_data!!!:", con.execute(f"SELECT COUNT(*) FROM {raw_schema}.stock_daily_data").fetchone()[0]) # type: ignore

    #### RAW TRADE DATA ####

    # Create trades_data table with only the relevant files
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {raw_schema}.all_options_trades_data (
                option_ticker VARCHAR,
                security VARCHAR,
                option_type VARCHAR,
                strike_price DOUBLE,
                expiration DATE,
                conditions INT,
                correction INT,
                exchange INT,
                price DOUBLE,
                sip_timestamp BIGINT,
                size INT,
                trade_value DOUBLE,
                data_date DATE
            )
    """)
    print(f"Created {raw_schema}.all_options_trades_data db table")

    option_trade_files = get_files_to_load('all_options_trades_data',option_trade_dir, num_files_to_load, con)
    # Load only the new files
    if option_trade_files:
        total_batches = ((len(option_trade_files) - 1) // batch_size) + 1
        for i in range(0, len(option_trade_files), batch_size):
            batch = option_trade_files[i:i + batch_size]
            print(f"Loading batch {i // batch_size + 1} of {total_batches} for all_options_trades_data")
            con.execute(f"""
                INSERT INTO {raw_schema}.all_options_trades_data
                SELECT 
                    ticker AS option_ticker,
                    REGEXP_EXTRACT(ticker, '^O:([A-Z]+)\d{{0,1}}\d{{6}}[CP]\d{{8}}$', 1) AS security,
                    REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}\d{{6}}([CP])\d{{8}}$', 1) AS option_type,
                    CASE
                        WHEN REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}\d{{6}}[CP](\d{{8}})$', 1) != ''
                        THEN REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}\d{{6}}[CP](\d{{8}})$', 1)::DOUBLE / 1000.0 
                        ELSE NULL
                    END  AS strike_price,
                    CASE
                        WHEN REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}(\d{{6}})[CP]\d{{8}}$', 1) != ''
                        THEN STRPTIME(REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}(\d{{6}})[CP]\d{{8}}$', 1), '%y%m%d')::DATE
                        ELSE NULL
                    END AS expiration,
                    conditions,
                    correction,
                    exchange,
                    price,
                    sip_timestamp,
                    size,
                    price * size * 100 AS trade_value,
                    CAST(
                        CASE
                            WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv.gz$', 1) != '' 
                            THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv.gz$', 1)
                            ELSE NULL
                        END AS DATE
                    ) AS data_date
                FROM read_csv_auto({batch}, filename=True, compression='gzip')
            """)
        print(f"Loaded data from {len(option_trade_files)} new files into {raw_schema}.all_options_trades_data")
    else:
        print(f"No new data to load to {raw_schema}.all_options_trades_data.")
    print(f"!!!ROWS IN {raw_schema}.all_options_trades_data!!!:", con.execute(f"SELECT COUNT(*) FROM {raw_schema}.all_options_trades_data").fetchone()[0]) # type: ignore

    if sectors_industries_csv:
        con.execute(f"""
            CREATE OR REPLACE TABLE {raw_schema}.sector_industry AS
            SELECT 
                security,
                company_name,
                sector,
                industry
            FROM read_csv_auto('{sectors_industries_csv}', filename=True)
        """)
    else:
        print(f"No new data to load to {raw_schema}.sector_industry.")
    print(f"!!!ROWS IN {raw_schema}.sector_industry!!!:", con.execute(f"SELECT COUNT(*) FROM {raw_schema}.sector_industry").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

    # Capture and print end time, then calculate duration
    end_time = time.time()
    print(f"End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-files-to-load", type=int, default=config.NUM_FILES_TO_PROCESS)
    parser.add_argument("--batch-size", type=int, default=config.BATCH_SIZE)
    args = parser.parse_args()
    
    main(args.num_files_to_load, args.batch_size)