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
import json

### SETTINGS ###
# Define file paths
full_db_path = config.FULL_DB_PATH
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

# Set up API key
dataservices_path = config.DATASERVICES_PATH
API_KEY = get_static_string(dataservices_path, "API_KEY")

### RAW DATA ###
def main(batch_size):
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    # Create schema if not exists
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")
    print(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")

    #### OPTIONS AGGREGATES DATA ####

    # Create raw_options_quotes_seconds table
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {raw_schema}.raw_options_quotes_seconds (
            option_ticker VARCHAR,
            timestamp BIGINT,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            transactions BIGINT,
            data_date DATE
        )
    """)
    print(f"Created {raw_schema}.raw_options_quotes_seconds db table")

    # Get distinct data_dates in ascending order
    data_dates = con.execute(f"""
        SELECT DISTINCT data_date
        FROM {raw_schema}.all_options_trades_data
        ORDER BY data_date ASC
    """).fetchall()

    for data_date_tuple in data_dates:
        data_date = data_date_tuple[0]
        print(f"Processing data_date: {data_date}")

        # Get distinct option_tickers for this data_date in ascending order
        option_tickers = con.execute(f"""
            SELECT DISTINCT option_ticker
            FROM {raw_schema}.all_options_trades_data
            WHERE data_date = '{data_date}'
            ORDER BY option_ticker ASC
        """).fetchall()

        total_tickers = len(option_tickers)
        total_batches = ((total_tickers - 1) // batch_size) + 1

        for i in range(0, total_tickers, batch_size):
            batch = option_tickers[i:i + batch_size]
            print(f"Loading batch {i // batch_size + 1} of {total_batches} for data_date {data_date}")

            for option_ticker_tuple in batch:
                option_ticker = option_ticker_tuple[0]
                from_date = data_date.strftime("%Y-%m-%d")
                to_date = data_date.strftime("%Y-%m-%d")

                url = f"https://api.polygon.io/v2/aggs/ticker/{option_ticker}/range/1/second/{from_date}/{to_date}"
                params = {
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 50000,
                    "apiKey": API_KEY
                }

                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        insert_values = []
                        for result in results:
                            insert_values.append((
                                option_ticker,
                                result.get("t"),
                                result.get("o"),
                                result.get("h"),
                                result.get("l"),
                                result.get("c"),
                                result.get("v"),
                                result.get("n"),
                                data_date
                            ))

                        con.executemany(f"""
                            INSERT INTO {raw_schema}.raw_options_quotes_seconds
                            (option_ticker, timestamp, open, high, low, close, volume, transactions, data_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, insert_values)
                        print(f"Inserted {len(results)} records for {option_ticker} on {data_date}")
                    else:
                        print(f"No data for {option_ticker} on {data_date}")
                else:
                    print(f"Failed to fetch data for {option_ticker} on {data_date}: {response.status_code} - {response.text}")

                # Sleep to respect rate limits (adjust as needed based on Polygon plan)
                time.sleep(0.2)  # Example: 5 requests per second

    print(f"!!!ROWS IN {raw_schema}.raw_options_quotes_seconds!!!:", con.execute(f"SELECT COUNT(*) FROM {raw_schema}.raw_options_quotes_seconds").fetchone()[0])

    # Explicitly close the connection
    con.close()

    # Capture and print end time, then calculate duration
    end_time = time.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=config.BATCH_SIZE)
    args = parser.parse_args()
    
    main(args.batch_size)