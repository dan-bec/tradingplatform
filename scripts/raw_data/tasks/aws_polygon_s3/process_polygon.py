import boto3
import gzip
import io
import json
import os
from datetime import datetime
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError
import requests
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Config
POLYGON_API_ENDPOINT = os.getenv('POLYGON_API_ENDPOINT', 'https://api.polygon.io')
TARGET_S3_BUCKET = os.getenv('TARGET_S3_BUCKET', 'bullseye-cap-polygon-data')
MAX_CHUNK_SIZE_BYTES = int(os.getenv('MAX_CHUNK_SIZE_BYTES', 4 * 1024 * 1024 * 1024))  # 4 GB (for safety, not used)

def fetch_quotes(ticker, date_str, timestamp_gte, timestamp_lte, api_key):
    """Fetch quotes for a ticker in a time window, return as CSV string."""
    url = f"{POLYGON_API_ENDPOINT}/v3/quotes/{ticker}"
    params = {
        'timestamp.gte': str(timestamp_gte),
        'timestamp.lte': str(timestamp_lte),
        'limit': 50000,  # Adjustable; max 50,000
        'order': 'asc',
        'sort': 'sip_timestamp',
        'apiKey': api_key
    }
    headers = {'Accept-Encoding': 'gzip'}
    
    quotes = []
    for attempt in range(3):
        try:
            while url:
                response = requests.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                quotes.extend(data.get('results', []))
                url = data.get('next_url')
                if url:
                    params = None
                logging.info(f"Fetched {len(data.get('results', []))} quotes for {ticker}")
            break
        except requests.RequestException as e:
            if attempt == 2:
                logging.error(f"Failed to fetch quotes for {ticker}: {e}")
                raise
            logging.warning(f"Retry {attempt+1} for {ticker}: {e}")
            time.sleep(2 ** attempt)
    
    # Convert to CSV
    if not quotes:
        return None
    csv_buffer = io.StringIO()
    csv_buffer.write("ticker,bid_exchange,bid_price,bid_size,ask_exchange,ask_price,ask_size,sip_timestamp\n")
    for quote in quotes:
        csv_buffer.write(f"{quote['ticker']},{quote.get('bid_exchange', '')},{quote.get('bid_price', '')},{quote.get('bid_size', '')},{quote.get('ask_exchange', '')},{quote.get('ask_price', '')},{quote.get('ask_size', '')},{quote.get('sip_timestamp', '')}\n")
    return csv_buffer.getvalue()

def process_chunk(chunk_index, date_str, target_s3, api_keys):
    """Process a chunk of compressed intervals, write one .csv.gz per API call."""
    transfer_config = TransferConfig(
        multipart_threshold=1024*1024*1024,
        max_concurrency=8,  # Fixed for 4 vCPUs
        num_download_attempts=5,
        max_io_queue=10000
    )
    
    # Load chunk from S3
    s3_key = f"options/quotes/{date_str}/compressed_chunk_{chunk_index}.json"
    try:
        response = target_s3.get_object(Bucket=TARGET_S3_BUCKET, Key=s3_key)
        intervals = json.loads(response['Body'].read().decode('utf-8'))
        print(f"Loaded {len(intervals)} intervals from s3://{TARGET_S3_BUCKET}/{s3_key}")
    except ClientError as e:
        logging.error(f"Failed to load chunk {chunk_index}: {e}")
        raise

    # Process intervals in parallel
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for i, interval in enumerate(intervals):
            ticker = interval['ticker']
            gte = interval['timestamp_gte']
            lte = interval['timestamp_lte']
            api_key = api_keys[i % len(api_keys)]  # Rotate keys
            futures.append(executor.submit(fetch_quotes, ticker, date_str, gte, lte, api_key))
        
        for i, future in enumerate(as_completed(futures)):
            try:
                csv_data = future.result()
                if csv_data:
                    interval = intervals[i]
                    ticker = interval['ticker']
                    gte = interval['timestamp_gte']
                    lte = interval['timestamp_lte']
                    part_key = f"options/quotes/{date_str}/ticker_{ticker}_gte_{gte}_lte_{lte}.csv.gz"
                    csv_buffer = io.BytesIO()
                    with gzip.GzipFile(fileobj=csv_buffer, mode='wb') as gz:
                        gz.write(csv_data.encode('utf-8'))
                    csv_buffer.seek(0)
                    for attempt in range(3):
                        try:
                            target_s3.upload_fileobj(
                                csv_buffer,
                                Bucket=TARGET_S3_BUCKET,
                                Key=part_key,
                                Config=transfer_config
                            )
                            print(f"Uploaded {part_key} to s3://{TARGET_S3_BUCKET}/{part_key}")
                            break
                        except ClientError as e:
                            if attempt == 2:
                                raise
                            logging.warning(f"Retry {attempt+1} for {part_key} upload: {e}")
                            time.sleep(2 ** attempt)
            except Exception as e:
                logging.error(f"Error processing interval {i}: {e}")
                raise

def main(date_str, chunk_index):
    logging.info(f"Starting processing for date: {date_str}, chunk_index: {chunk_index}")
    # Fetch secrets
    session = boto3.Session()
    secrets_client = session.client('secretsmanager', region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
    response = secrets_client.get_secret_value(SecretId='polygon-credentials')
    secret_dict = json.loads(response['SecretString'])
    api_keys = [secret_dict['api_key']]  # Add more keys: ['api_key1', 'api_key2']
    
    target_s3 = session.client('s3')
    
    process_chunk(chunk_index, date_str, target_s3, api_keys)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--chunk-index", type=int, required=True, help="Index of the chunk to process")
    args = parser.parse_args()
    main(args.date, args.chunk_index)