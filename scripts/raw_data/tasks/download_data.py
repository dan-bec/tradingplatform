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
import os
import boto3
from botocore.config import Config
import requests
import pandas as pd
import re
from datetime import datetime, timedelta
import argparse

# Configuration
script_dir = config.REPO_ROOT
dataservices_path = config.DATASERVICES_PATH
S3_ENDPOINT = config.S3_ENDPOINT
BUCKET_NAME = config.BUCKET_NAME

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

    '''
    {
        "prefix": "us_stocks_sip/trades_v1",
        "download_dir": config.STOCK_TRADE_DIR,
        "description": "Stocks Trades"
    },
    {
        "prefix": "us_stocks_sip/quotes_v1",
        "download_dir": config.STOCK_QUOTES_DIR,
        "description": "Stocks Trades"
    },
    {
        "prefix": "us_options_opra/quotes_v1",
        "download_dir": config.OPTION_QUOTES_DIR,
        "description": "Options Quotes"
    },
    '''
# Define multiple passes with their respective configurations
PASSES = [
    {
        "prefix": "us_stocks_sip/day_aggs_v1",
        "download_dir": config.STOCK_SUMMARY_DIR,
        "description": "Stocks Daily Aggregates"
    },
    {
        "prefix": "us_stocks_sip/minute_aggs_v1",
        "download_dir": config.STOCK_MINUTE_DIR,
        "description": "Stocks Minute Aggregates"
    },
    {
        "prefix": "us_options_opra/day_aggs_v1",
        "download_dir": config.OPTION_SUMMARY_DIR,
        "description": "Options Daily Aggregates"
    },
    {
        "prefix": "us_options_opra/trades_v1",
        "download_dir": config.OPTION_TRADE_DIR,
        "description": "Options Trades"
    },
    {
        "prefix": "us_options_opra/minute_aggs_v1",
        "download_dir": config.OPTION_MINUTE_DIR,
        "description": "Options Minute Aggregates"
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
    """Download the gzip file for a given date, prefix, and local directory, skipping if it already exists."""
    gz_file_name = f"{date}.csv.gz"
    s3_key = f"{s3_prefix}/{date[:4]}/{date[5:7]}/{gz_file_name}"
    local_gz_path = download_dir / gz_file_name
    
    if local_gz_path.exists():
        print(f"Skipping {s3_key}: Gzip file already exists at {local_gz_path}")
        return
    
    try:
        s3.download_file(BUCKET_NAME, s3_key, str(local_gz_path))
        print(f"Successfully downloaded: {s3_key} to {local_gz_path}")
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
    
    download_dir.mkdir(parents=True, exist_ok=True)
    
    dates = generate_date_list(start_date, end_date)
    print(f"Processing {description} for dates: {start_date} to {end_date}")
    
    for date in dates:
        download_file(date, prefix, download_dir)
    
    print(f"Completed {description} pass.")

def main(start_date, end_date):

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    """Execute all configured passes to download files."""
    for pass_config in PASSES:
        process_pass(pass_config, start_dt, end_dt)
    print("All download passes completed.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, default=config.START_DATE)
    parser.add_argument("--end-date", type=str, default=config.END_DATE)
    args = parser.parse_args()

    main(args.start_date, args.end_date)