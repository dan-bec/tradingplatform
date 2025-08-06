import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue

# Determine the project root dynamically
FILE_DIR = Path(__file__)
TASK_SCRIPT_DIR = FILE_DIR.parent
REPO_ROOT = TASK_SCRIPT_DIR.parents[2]  
FILE_NAME = FILE_DIR.relative_to(REPO_ROOT)

# Insert the project root into sys.path if not already present
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.raw_data.config as config
import scripts.unusual_baselining.config as ub_config
import re
from datetime import datetime, date, time
import requests
import time as time_module
import duckdb
import json
import csv
import gzip
import urllib.parse
from collections import defaultdict

### SETTINGS ###
# Define file paths and constants
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
MAX_RETRIES = config.MAX_RETRIES  # Number of retry attempts for timeouts
TIMEOUT_SECONDS = config.TIMEOUT_SECONDS  # Timeout duration for API requests
MAX_CONCURRENT_REQUESTS = 5  # Max concurrent API calls (adjust based on Polygon plan)
REQUESTS_PER_MINUTE = 6000  # Adjust based on Polygon API plan (e.g., 5 for free tier)

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

# Function to append API key to URL
def append_api_key(url, api_key):
    """Append apiKey to the URL if not already present."""
    parsed_url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    if 'apiKey' not in query_params:
        query_params['apiKey'] = api_key
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        return urllib.parse.urlunparse(
            (parsed_url.scheme, parsed_url.netloc, parsed_url.path,
             parsed_url.params, new_query, parsed_url.fragment)
        )
    return url

# Function to convert date to datetime
def date_to_datetime(date_input):
    """Convert a date to datetime at start of day."""
    if isinstance(date_input, str):
        date_obj = datetime.strptime(date_input, '%Y-%m-%d').date()
    elif isinstance(date_input, date):
        date_obj = date_input
    else:
        raise ValueError("Input must be a datetime.date object or string in 'YYYY-MM-DD' format")
    return datetime.combine(date_obj, time(0, 0, 0))

# Function to convert date to Unix timestamp for end of day
def date_to_end_of_day_timestamp(date_input):
    """Convert a date to Unix timestamp for end of day (23:59:59)."""
    if isinstance(date_input, str):
        date_obj = datetime.strptime(date_input, '%Y-%m-%d').date()
    elif isinstance(date_input, date):
        date_obj = date_input
    else:
        raise ValueError("Input must be a datetime.date object or string in 'YYYY-MM-DD' format")
    end_of_day = datetime.combine(date_obj, time(23, 59, 59))
    return int(end_of_day.timestamp())

# Function to merge overlapping time ranges
def merge_overlapping_ranges(option_tickers, gap_tolerance=1_000_000_000):
    """
    Merge overlapping or near-contiguous time ranges for each option_ticker.
    
    Args:
        option_tickers (list of tuples): List of (option_ticker, timestamp_gte, timestamp_lte)
        gap_tolerance (int): Max gap (in nanoseconds) to merge ranges (default: 1,000,000 ns = 1 ms)
    
    Returns:
        list of tuples: Merged (option_ticker, timestamp_gte, timestamp_lte), sorted by ticker
    """
    # Group ranges by option_ticker
    groups = defaultdict(list)
    for ticker, gte, lte in option_tickers:
        groups[ticker].append((gte, lte))
    
    merged_results = []
    
    for ticker, ranges in groups.items():
        # Sort ranges by gte
        ranges.sort(key=lambda x: x[0])
        
        # Merge overlapping or near-contiguous ranges
        merged = []
        for current in ranges:
            if not merged:
                merged.append(list(current))
            else:
                prev = merged[-1]
                if current[0] <= prev[1] + gap_tolerance:
                    # Overlap or within tolerance: merge by updating end
                    prev[1] = max(prev[1], current[1])
                else:
                    merged.append(list(current))
        
        # Add merged ranges to results as tuples
        for gte, lte in merged:
            merged_results.append((ticker, gte, lte))
    
    # Sort final results by ticker
    merged_results.sort(key=lambda x: x[0])
    
    return merged_results

# Function to fetch quotes for a single option_ticker and time band
def fetch_quotes(option_ticker, timestamp_gte, timestamp_lte, data_date, semaphore):
    """Fetch quotes from Polygon API for a given ticker and time band."""
    rows = []
    url = f"https://api.polygon.io/v3/quotes/{option_ticker}?timestamp.gte={timestamp_gte}&timestamp.lte={timestamp_lte}&sort=timestamp&order=asc&limit=50000&apiKey={API_KEY}"
    total_fetched = 0
    page_count = 0
    retry_count = 0

    with semaphore:  # Limit concurrent requests
        while url:
            url = append_api_key(url, API_KEY)
            try:
                response = requests.get(url, timeout=TIMEOUT_SECONDS)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "OK":
                    print(f"API error for {option_ticker} on {data_date}: {data.get('error', 'Unknown error')}")
                    break

                results = data.get("results", [])
                if results:
                    for result in results:
                        rows.append((
                            option_ticker,
                            result.get("ask_exchange"),
                            result.get("ask_price"),
                            result.get("ask_size"),
                            result.get("bid_exchange"),
                            result.get("bid_price"),
                            result.get("bid_size"),
                            json.dumps(result.get("conditions", [])),
                            json.dumps(result.get("indicators", [])),
                            result.get("participant_timestamp"),
                            result.get("sequence_number"),
                            result.get("sip_timestamp"),
                            result.get("tape"),
                            data_date
                        ))
                    total_fetched += len(results)
                    page_count += 1
                    print(f"Fetched {len(results)} records for {option_ticker} on {data_date} (page {page_count}, total: {total_fetched}, time band: {timestamp_gte} to {timestamp_lte})")

                if "next_url" in data and data["next_url"]:
                    url = data["next_url"]
                    retry_count = 0
                else:
                    url = None

            except requests.exceptions.HTTPError as http_err:
                if response.status_code == 429: # type: ignore
                    print(f"Rate limit exceeded for {option_ticker} on {data_date}. Waiting and retrying...")
                    time_module.sleep(60)
                    continue
                else:
                    print(f"HTTP error for {option_ticker} on {data_date}: {http_err}, Response: {response.text}") # type: ignore
                    break
            except requests.exceptions.RequestException as req_err:
                retry_count += 1
                if retry_count <= MAX_RETRIES:
                    print(f"Request error for {option_ticker} on {data_date} (attempt {retry_count}/{MAX_RETRIES}): {req_err}")
                    time_module.sleep(10 * retry_count)
                    continue
                else:
                    print(f"Max retries ({MAX_RETRIES}) exceeded for {option_ticker} on {data_date}: {req_err}")
                    break
            except ValueError as json_err:
                print(f"JSON decode error for {option_ticker} on {data_date}: {json_err}, Response: {response.text}") # type: ignore
                break

            # Sleep to respect rate limits
            time_module.sleep(0.2)

    if total_fetched > 0:
        print(f"Completed fetching {total_fetched} records for {option_ticker} on {data_date}")
    else:
        print(f"No data for {option_ticker} on {data_date} in time band {timestamp_gte} to {timestamp_lte}")

    return rows

### RAW DATA ###
def main(batch_size):
    # Capture and print start time
    start_time = time_module.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    # Create schema if not exists
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")
    print(f"CREATE SCHEMA IF NOT EXISTS {raw_schema}")

    #### OPTIONS QUOTES DATA ####

    # Create raw_options_quotes_seconds table with next_sip_timestamp
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {raw_schema}.raw_options_quotes_seconds (
            option_ticker VARCHAR,
            ask_exchange INTEGER,
            ask_price DOUBLE,
            ask_size INTEGER,
            bid_exchange INTEGER,
            bid_price DOUBLE,
            bid_size INTEGER,
            conditions VARCHAR,
            indicators VARCHAR,
            participant_timestamp BIGINT,
            sequence_number BIGINT,
            sip_timestamp BIGINT,
            tape INTEGER,
            data_date DATE,
            next_sip_timestamp BIGINT
        )
    """)
    print(f"Created {raw_schema}.raw_options_quotes_seconds db table")

    # Get distinct data_dates in ascending order
    data_dates = con.execute(f"""
        SELECT DISTINCT data_date
        FROM {raw_schema}.all_options_trades_data
        WHERE data_date = '2023-06-22'
        ORDER BY data_date ASC
    """).fetchall()

    # Semaphore to limit concurrent requests
    semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

    for data_date_tuple in data_dates:
        data_date = data_date_tuple[0]
        print(f"Processing data_date: {data_date}")

        # Check if CSV file already exists
        option_quotes_dir = config.OPTION_QUOTES_DIR
        option_quotes_dir.mkdir(parents=True, exist_ok=True)
        file_path = option_quotes_dir / f"{data_date.strftime('%Y-%m-%d')}.csv.gz"
        if file_path.exists():
            print(f"CSV file {file_path} already exists, skipping data collection and loading for {data_date}.")
            continue

        # Get distinct option_tickers with time bands for this data_date that are not yet loaded
        option_tickers = con.execute(f"""
            SELECT DISTINCT t.option_ticker, 
                           t.sip_timestamp - 30_000_000_000 AS timestamp_gte, 
                           t.sip_timestamp + 30_000_000_000 AS timestamp_lte
            FROM {raw_schema}.all_options_trades_data t
            LEFT JOIN (
                SELECT DISTINCT option_ticker
                FROM {raw_schema}.raw_options_quotes_seconds
                WHERE data_date = '{data_date}'
            ) q ON t.option_ticker = q.option_ticker
            WHERE t.data_date = '{data_date}' 
                AND t.trade_value >= {ub_config.MIN_TRADE_VALUE}
                AND q.option_ticker IS NULL 
            ORDER BY t.option_ticker ASC
        """).fetchall()

        if not option_tickers:
            print(f"No new option_tickers to load for {data_date}, skipping.")
            continue

        # Merge overlapping time ranges
        option_tickers = merge_overlapping_ranges(option_tickers, gap_tolerance=1000000)
        print(f"Merged {len(option_tickers)} time ranges for {data_date}")

        rows = []
        rows_lock = threading.Lock()  # Lock for thread-safe appending to rows

        total_tickers = len(option_tickers)
        total_batches = ((total_tickers - 1) // batch_size) + 1

        # Convert date to Unix timestamp for end of day (for next_sip_timestamp)
        end_timestamp = date_to_end_of_day_timestamp(data_date)

        for i in range(0, total_tickers, batch_size):
            batch = option_tickers[i:i + batch_size]
            print(f"Processing batch {i // batch_size + 1} of {total_batches} for data_date {data_date}")

            # Parallelize API calls within the batch
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
                future_to_params = {
                    executor.submit(fetch_quotes, ticker, gte, lte, data_date, semaphore): (ticker, gte, lte)
                    for ticker, gte, lte in batch
                }
                for future in as_completed(future_to_params):
                    ticker, gte, lte = future_to_params[future]
                    try:
                        batch_rows = future.result()
                        with rows_lock:
                            rows.extend(batch_rows)
                    except Exception as exc:
                        print(f"Exception for {ticker} on {data_date} in time band {gte} to {lte}: {exc}")

            # Sleep to respect per-minute rate limits (e.g., 5 requests per minute for free tier)
            time_module.sleep(60 / REQUESTS_PER_MINUTE)

        if rows:
            # Deduplicate rows based on all columns
            rows = list(dict.fromkeys([tuple(row) for row in rows]))
            print(f"Deduplicated rows for {data_date}: {len(rows)} unique rows remaining")

            with gzip.open(file_path, 'wt', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['option_ticker', 'ask_exchange', 'ask_price', 'ask_size', 'bid_exchange', 'bid_price', 'bid_size', 'conditions', 'indicators', 'participant_timestamp', 'sequence_number', 'sip_timestamp', 'tape', 'data_date'])
                writer.writerows(rows)

            print(f"Wrote {len(rows)} rows to {file_path}")

            # Load data into a temporary table
            temp_table = f"{raw_schema}.temp_options_quotes_seconds"
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE {temp_table} (
                    option_ticker VARCHAR,
                    ask_exchange INTEGER,
                    ask_price DOUBLE,
                    ask_size INTEGER,
                    bid_exchange INTEGER,
                    bid_price DOUBLE,
                    bid_size INTEGER,
                    conditions VARCHAR,
                    indicators VARCHAR,
                    participant_timestamp BIGINT,
                    sequence_number BIGINT,
                    sip_timestamp BIGINT,
                    tape INTEGER,
                    data_date DATE
                )
            """)
            con.execute(f"""
                INSERT INTO {temp_table}
                SELECT * FROM read_csv_auto('{str(file_path)}', compression='gzip')
            """)

            # Compute next_sip_timestamp and insert into main table
            con.execute(f"""
                INSERT INTO {raw_schema}.raw_options_quotes_seconds
                SELECT
                    option_ticker,
                    ask_exchange,
                    ask_price,
                    ask_size,
                    bid_exchange,
                    bid_price,
                    bid_size,
                    conditions,
                    indicators,
                    participant_timestamp,
                    sequence_number,
                    sip_timestamp,
                    tape,
                    data_date,
                    COALESCE(
                        LEAD(sip_timestamp) OVER (PARTITION BY data_date, option_ticker ORDER BY sip_timestamp),
                        {end_timestamp}
                    ) AS next_sip_timestamp
                FROM {temp_table}
            """)
            print(f"Loaded data from {file_path} into {raw_schema}.raw_options_quotes_seconds with next_sip_timestamp")

    print(f"!!!ROWS IN {raw_schema}.raw_options_quotes_seconds!!!:", con.execute(f"SELECT COUNT(*) FROM {raw_schema}.raw_options_quotes_seconds").fetchone()[0]) # type: ignore

    # Explicitly close the connection
    con.close()

    # Capture and print end time, then calculate duration
    end_time = time_module.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=config.BATCH_SIZE)
    args = parser.parse_args()
    
    main(args.batch_size)