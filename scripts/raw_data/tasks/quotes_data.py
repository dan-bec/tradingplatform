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
import boto3
from botocore.config import Config
import duckdb
from datetime import datetime, timedelta, time
import time
import os
import gc

# Configuration
s3_endpoint = config.S3_ENDPOINT
bucket_name = config.BUCKET_NAME
full_db_path = config.FULL_DB_PATH
start_date = datetime.strptime(config.START_DATE, "%Y-%m-%d").date()
end_date = datetime.strptime(config.END_DATE, "%Y-%m-%d").date()
raw_schema = config.RAW_SCHEMA
quotes_prefix = "us_options_opra/quotes_v1"
options_quotes_dir = config.OPTION_QUOTES_DIR
options_quotes_dir.mkdir(parents=True, exist_ok=True)

# AWS credentials
dataservices_path = config.DATASERVICES_PATH
AWS_ACCESS_KEY = config.get_static_string(dataservices_path, "AWS_ACCESS_KEY")
AWS_SECRET_KEY = config.get_static_string(dataservices_path, "AWS_SECRET_KEY")

# Set up S3 client
session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)
s3 = session.client(
    's3',
    endpoint_url=s3_endpoint,
    config=Config(signature_version='s3v4'),
)

def generate_date_list(start, end):
    """Generate a list of dates between start and end."""
    date_list = []
    current_date = start
    while current_date <= end:
        date_list.append(current_date)
        current_date += timedelta(days=1)
    return date_list

def get_existing_dates():
    """Retrieve the list of existing data_dates from the option_quotes table."""
    try:
        con = duckdb.connect(str(full_db_path))
        existing_dates = con.execute(f"SELECT DISTINCT data_date FROM {raw_schema}.option_quotes").fetchall()
        con.close()
        return set(date[0] for date in existing_dates)
    except duckdb.CatalogException:
        # If the table does not exist, return an empty set
        return set()

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

def process_date(date):
    """Process a single date's quotes file."""
    date_str = date.strftime("%Y-%m-%d")
    year = date.strftime("%Y")
    month = date.strftime("%m")
    s3_key = f"{quotes_prefix}/{year}/{month}/{date_str}.csv.gz"
    # Convert date to Unix timestamp for end of day (for next_sip_timestamp)
    end_timestamp = date_to_end_of_day_timestamp(date)    
    print(end_timestamp)

    sys.exit()

    # Define the local file path in options_quotes_dir
    local_file = options_quotes_dir / f"{date_str}.csv.gz"
    
    try:
        # Download the quotes file from S3
        s3.download_file(bucket_name, s3_key, str(local_file))
        print(f"Downloaded {s3_key} to {local_file}")

        # Trigger garbage collection
        gc.collect()

        # Set up DuckDB connection
        con = duckdb.connect(str(full_db_path))
        
        # Create a staging table for the quotes data
        con.execute(f"""
        CREATE TABLE IF NOT EXISTS {raw_schema}.staging_quotes_raw (
            option_ticker VARCHAR,
            sip_timestamp BIGINT,
            bid_price DOUBLE,
            ask_price DOUBLE,
            bid_size INT,
            ask_size INT,
            bid_exchange INT,
            ask_exchange INT,
            data_date DATE
        )
        """)
        
        # Load the downloaded file into the staging table
        con.execute(f"""
        INSERT INTO {raw_schema}.staging_quotes_raw
        SELECT 
            ticker AS option_ticker,
            sip_timestamp,
            bid_price,
            ask_price,
            bid_size,
            ask_size,
            bid_exchange,
            ask_exchange,
            CAST('{date_str}' AS DATE) AS data_date
        FROM read_csv_auto('{local_file}', compression='gzip')
        """)
        print(f"Loaded {local_file} into {raw_schema}.staging_quotes_raw")

        # Trigger garbage collection
        gc.collect()

        # Create a staging table for the quotes data
        con.execute(f"""
        CREATE TABLE IF NOT EXISTS {raw_schema}.staging_quotes_window (
            option_ticker VARCHAR,
            sip_timestamp BIGINT,
            next_sip_timestamp BIGINT,
            bid_price DOUBLE,
            ask_price DOUBLE,
            bid_size INT,
            ask_size INT,
            bid_exchange INT,
            ask_exchange INT,
            data_date DATE
        )
        """)
        
        # Load the downloaded file into the staging table
        con.execute(f"""
        INSERT INTO {raw_schema}.staging_quotes_window
        SELECT 
            option_ticker,
            sip_timestamp,
            COALESCE(
                LEAD(sip_timestamp) OVER (PARTITION BY data_date, option_ticker ORDER BY sip_timestamp),
                {end_timestamp}
            ) AS next_sip_timestamp,
            bid_price,
            ask_price,
            bid_size,
            ask_size,
            bid_exchange,
            ask_exchange,
            data_date
        FROM {raw_schema}.staging_quotes_raw q
        """)
        print(f"Loaded {raw_schema}.staging_quotes_raw into {raw_schema}.staging_quotes_window")

        # Drop the staging table
        con.execute(f"DROP TABLE {raw_schema}.staging_quotes_raw")
        print(f"DROP TABLE {raw_schema}.staging_quotes_raw SUCCESSFUL")

        # Trigger garbage collection
        gc.collect()
      
        # Join with trades data and insert into final table
        con.execute(f"""
        INSERT INTO {raw_schema}.option_quotes
        SELECT DISTINCT
            q.data_date,
            q.option_ticker,
            q.sip_timestamp,
            q.next_sip_timestamp,
            q.bid_price,
            q.ask_price,
            q.bid_size,
            q.ask_size,
            q.bid_exchange,
            q.ask_exchange
        FROM {raw_schema}.staging_quotes_window q
        JOIN {raw_schema}.all_options_trades_data ot
            ON q.data_date = ot.data_date
            AND q.option_ticker = ot.option_ticker
            AND ot.sip_timestamp between q.sip_timestamp and q.next_timestamp
        """)
        print(f"Loaded {raw_schema}.staging_quotes_window into {raw_schema}.option_quotes")
        
        # Drop the staging table
        con.execute(f"DROP TABLE {raw_schema}.staging_quotes_window")
        print(f"Processed data for {date_str}")

        con.close()
 
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"File not found: {s3_key}")
        else:
            raise e
    except Exception as e:
        print(f"Error processing {date_str}: {e}")
    finally:
        # Clean up the downloaded file
        if local_file.exists():
            os.remove(local_file)
            print(f"Deleted {local_file}")

def main():
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    # Set up DuckDB connection
    con = duckdb.connect(str(full_db_path))

    # Create the final table if it doesn't exist
    con.execute(f"""
    CREATE TABLE IF NOT EXISTS {raw_schema}.option_quotes (
        data_date DATE,
        option_ticker VARCHAR,
        sip_timestamp BIGINT,
        next_sip_timestamp BIGINT,
        bid_price DOUBLE,
        ask_price DOUBLE,
        bid_size INT,
        ask_size INT,
        bid_exchange INT,
        ask_exchange INT
    )
    """)

    con.close()

    """Main function to process all dates in the range that are not already in the database."""
    all_dates = generate_date_list(start_date, end_date)
    existing_dates = get_existing_dates()
    dates_to_process = [date for date in all_dates if date not in existing_dates]

    for date in dates_to_process:
        print(f"Processing data for {date}")
        process_date(date)
    
    # Capture and print end time, then calculate duration
    end_time = time.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    main()