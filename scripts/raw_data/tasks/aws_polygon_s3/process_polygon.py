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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Config
POLYGON_ENDPOINT = os.getenv('POLYGON_ENDPOINT', 'https://files.polygon.io')
POLYGON_BUCKET = os.getenv('POLYGON_BUCKET', 'flatfiles')
TARGET_S3_BUCKET = os.getenv('TARGET_S3_BUCKET', 'bullseye-cap-polygon-data')
MAX_CHUNK_SIZE_BYTES = int(os.getenv('MAX_CHUNK_SIZE_BYTES', 4 * 1024 * 1024 * 1024))  # 4 GB
CHECK_INTERVAL_LINES = int(os.getenv('CHECK_INTERVAL_LINES', 1000))

# Polygon passes
PASSES = [
    {"prefix": "us_options_opra/trades_v1", "s3_folder": "options/trades"},
    {"prefix": "us_options_opra/quotes_v1", "s3_folder": "options/quotes"}
]

def date_folder_exists(s3_folder, target_s3, date_str):
    response = target_s3.list_objects_v2(Bucket=TARGET_S3_BUCKET, Prefix=f"{s3_folder}/{date_str}/", MaxKeys=1)
    return 'Contents' in response

def process_file(prefix, s3_folder, date_str, polygon_s3, target_s3, num_workers):
    gz_key = f"{prefix}/{date_str[:4]}/{date_str[5:7]}/{date_str}.csv.gz"
    if date_folder_exists(s3_folder, target_s3, date_str):
        print(f"Skipping {gz_key}")
        return

    try:
        # Get file metadata
        logging.info(f"Processing {gz_key}")
        head = polygon_s3.head_object(Bucket=POLYGON_BUCKET, Key=gz_key)
        file_size = head['ContentLength']
        print(f"{gz_key} size: {file_size / (1024*1024):.2f} MB")

        # Stream download
        transfer_config = TransferConfig(
            multipart_threshold=1024*1024*1024,  # 1 GB
            max_concurrency=num_workers * 2,  # 2x threads per vCPU
            num_download_attempts=5,
            max_io_queue=10000
        )
        response = polygon_s3.get_object(Bucket=POLYGON_BUCKET, Key=gz_key)
        gz_stream = response['Body']

        # Stream decompress, chunk, and upload
        with gzip.open(gz_stream, 'rt') as input_file:
            header = input_file.readline()
            if not header:
                print(f"Empty file {gz_key}, skipping")
                return
            
            chunk_id = 0
            line_count = 0
            while True:
                chunk_buffer = io.BytesIO()
                with gzip.GzipFile(fileobj=chunk_buffer, mode='wb') as chunk_gz:
                    chunk_gz.write(header.encode('utf-8'))
                    lines_written = 0
                    for line in input_file:
                        chunk_gz.write(line.encode('utf-8'))
                        lines_written += 1
                        line_count += 1
                        if lines_written % CHECK_INTERVAL_LINES == 0:
                            chunk_gz.flush()
                            if chunk_buffer.tell() > MAX_CHUNK_SIZE_BYTES * 0.9:
                                break
                    if lines_written == 0:
                        break
                
                chunk_buffer.seek(0)
                chunk_size = chunk_buffer.getbuffer().nbytes
                if chunk_size == 0:
                    break
                
                part_key = f"{s3_folder}/{date_str}/part_{chunk_id:04d}.csv.gz"
                target_s3.upload_fileobj(
                    chunk_buffer,
                    Bucket=TARGET_S3_BUCKET,
                    Key=part_key,
                    Config=transfer_config
                )
                print(f"Uploaded chunk {chunk_id} ({chunk_size / (1024*1024):.2f} MB) to s3://{TARGET_S3_BUCKET}/{part_key}")
                logging.info(f"Processed {gz_key} into {chunk_id} chunks")
                chunk_id += 1
            
            print(f"Processed {gz_key} into {chunk_id} chunks")

    except polygon_s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"Skipping {gz_key}: Not found on Polygon")
        else:
            raise
    except Exception as e:
        print(f"Error processing {gz_key}: {e}")
        logging.error(f"Error processing {gz_key}: {e}", exc_info=True)
        raise

def main(date_str, num_workers):
    logging.info(f"Starting processing for date: {date_str} with {num_workers} workers")
    # Fetch secrets
    session = boto3.Session()
    secrets_client = session.client('secretsmanager', region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
    response = secrets_client.get_secret_value(SecretId='polygon-credentials')
    secret_dict = json.loads(response['SecretString'])
    POLYGON_ACCESS_KEY = secret_dict['access_key']
    POLYGON_SECRET_KEY = secret_dict['secret_key']

    polygon_s3 = boto3.client('s3', endpoint_url=POLYGON_ENDPOINT, aws_access_key_id=POLYGON_ACCESS_KEY,
                              aws_secret_access_key=POLYGON_SECRET_KEY, config=Config(signature_version='s3v4', retries={'max_attempts': 5}))

    target_s3 = session.client('s3')

    # Process files in parallel (quotes is heavy, trades light)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(process_file, pass_config['prefix'], pass_config['s3_folder'], date_str, polygon_s3, target_s3, num_workers)
                   for pass_config in PASSES]
        for future in as_completed(futures):
            future.result()  # Wait and handle errors

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    parser.add_argument("--num-workers", type=int, default=4, help="Number of worker threads for downloads")
    args = parser.parse_args()
    main(args.date, args.num_workers)