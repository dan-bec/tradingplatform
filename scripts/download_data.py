import os
import boto3
from botocore.config import Config
import requests
import pandas as pd
import re
from datetime import datetime, timedelta
from pathlib import Path
import gzip
import shutil

# Function to extract static string variables from DataServices.cs
def get_static_string(file_path, var_name):
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

# Configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
banks_csv_path = os.path.join(script_dir, "..", "data", "banks", "banks.csv")
banks_option_volume_csv_path = os.path.join(script_dir, "..", "data", "banks", "banks_daily_option_volume.csv")
dataservices_path = os.path.join(script_dir, "..", "src", "BullseyeApp", "Shared", "Data", "DataService.cs")
S3_ENDPOINT = "https://files.polygon.io"  # Polygon S3-compatible endpoint
BUCKET_NAME = "flatfiles"  # Polygon bucket name
START_DATE = datetime(2025, 1, 1).date()
END_DATE = datetime.now().date()  # Updated to include today

# Define multiple passes with their respective configurations
PASSES = [
    {
        "prefix": "us_stocks_sip/day_aggs_v1",
        "download_dir": Path("data/stocks/daily"),
        "description": "Stocks Daily Aggregates"
    },
    {
        "prefix": "us_options_opra/day_aggs_v1",
        "download_dir": Path("data/options/daily"),
        "description": "Options Daily Aggregates"
    },
    {
        "prefix": "us_options_opra/trades_v1",
        "download_dir": Path("data/options/trades"),
        "description": "Options Trades"
    }
]

# Retrieve AWS access and secret keys
AWS_ACCESS_KEY = get_static_string(dataservices_path, "AWS_ACCESS_KEY")
AWS_SECRET_KEY = get_static_string(dataservices_path, "AWS_SECRET_KEY")

# Initialize a session using your credentials
session = boto3.Session(
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
)

# Create a client with your session and specify the endpoint
s3 = session.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    config=Config(signature_version='s3v4'),
)

def generate_date_list(start, end):
    """Generate a list of dates between start and end (inclusive) as strings."""
    date_list = []
    current_date = start
    while current_date <= end:
        date_list.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)
    return date_list

def download_file(date, s3_prefix, download_dir):
    """Download and unarchive the options file for a given date, prefix, and local directory, skipping if .csv exists."""
    # File naming convention
    gz_file_name = f"{date}.csv.gz"
    csv_file_name = f"{date}.csv"
    # S3 key: {prefix}/YYYY/MM/YYYY-MM-DD.csv.gz
    s3_key = f"{s3_prefix}/{date[:4]}/{date[5:7]}/{gz_file_name}"
    # Local paths
    local_csv_path = download_dir / csv_file_name
    local_gz_path = download_dir / gz_file_name
    
    # Check if .csv file already exists
    if local_csv_path.exists():
        print(f"Skipping {s3_key}: Corresponding .csv file already exists at {local_csv_path}")
        return
    
    try:
        # Download .csv.gz file
        s3.download_file(BUCKET_NAME, s3_key, str(local_gz_path))
        print(f"Successfully downloaded: {s3_key} to {local_gz_path}")
        # Unarchive .csv.gz to .csv
        with gzip.open(local_gz_path, 'rb') as f_in:
            with open(local_csv_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out) # type: ignore
        print(f"Successfully unarchived to {local_csv_path}")
        # Delete .csv.gz file
        os.remove(local_gz_path)
        print(f"Deleted {local_gz_path}")
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Skipping {s3_key}: File not found on S3")
        else:
            print(f"Failed to download {s3_key}: {e}")
    except Exception as e:
        print(f"Failed to process {s3_key}: {e}")

def process_pass(pass_config, start_date, end_date):
    """Process a single pass for downloading files with given configuration."""
    prefix = pass_config["prefix"]
    download_dir = pass_config["download_dir"]
    description = pass_config["description"]
    
    # Ensure local directory exists
    download_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate list of dates
    dates = generate_date_list(start_date, end_date)
    print(f"Processing {description} for dates: {start_date} to {end_date}")
    
    # Download files for each date
    for date in dates:
        download_file(date, prefix, download_dir)
    
    print(f"Completed {description} pass.")

def main():
    """Execute all configured passes to download files."""
    for pass_config in PASSES:
        process_pass(pass_config, START_DATE, END_DATE)
    print("All download passes completed.")

if __name__ == "__main__":
    main()