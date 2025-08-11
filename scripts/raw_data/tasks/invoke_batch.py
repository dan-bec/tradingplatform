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
from datetime import datetime, timedelta
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import duckdb
import json
import math

TARGET_S3_BUCKET = 'bullseye-cap-polygon-data'
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA

def generate_date_list(start_date, end_date):
    """Generate list of dates (YYYY-MM-DD) from start_date to end_date."""
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    date_list = []
    current = start
    while current <= end:
        date_list.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return date_list

def compress_intervals(con, raw_schema, data_date):
    """Compress overlapping time windows from DuckDB query into minimal non-overlapping intervals."""
    query = f"""
        SELECT DISTINCT t.option_ticker, 
                       t.sip_timestamp - 30_000_000_000 AS timestamp_gte, 
                       t.sip_timestamp + 30_000_000_000 AS timestamp_lte
        FROM {raw_schema}.all_options_trades_data t
        WHERE t.data_date = '{data_date}' 
        ORDER BY t.option_ticker ASC
    """
    result = con.execute(query).fetchdf()
    
    grouped = result.groupby('option_ticker')
    compressed_intervals = []
    
    for ticker, group in grouped:
        intervals = sorted(zip(group['timestamp_gte'], group['timestamp_lte']), key=lambda x: x[0])
        merged = []
        current_gte, current_lte = intervals[0]
        
        for gte, lte in intervals[1:]:
            if gte <= current_lte:
                current_lte = max(current_lte, lte)
            else:
                merged.append({'ticker': ticker, 'timestamp_gte': int(current_gte), 'timestamp_lte': int(current_lte)})
                current_gte, current_lte = gte, lte
        
        merged.append({'ticker': ticker, 'timestamp_gte': int(current_gte), 'timestamp_lte': int(current_lte)})
        compressed_intervals.extend(merged)
    
    compressed_intervals.sort(key=lambda x: (x['ticker'], x['timestamp_gte']))
    return compressed_intervals

def save_compressed_intervals_to_s3(s3_client, bucket, data_date, compressed_intervals, num_chunks):
    """Split compressed intervals into chunks and upload to S3 for parallel processing."""
    chunk_size = max(1, math.ceil(len(compressed_intervals) / num_chunks))
    for i in range(num_chunks):
        chunk = compressed_intervals[i * chunk_size:(i + 1) * chunk_size]
        key = f"options/quotes/{data_date}/compressed_chunk_{i}.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(chunk),
            ContentType='application/json'
        )
        print(f"Uploaded chunk {i} ({len(chunk)} intervals) to s3://{bucket}/{key}")

def update_job_definition(batch_client, job_def_name, image_tag, vcpus):
    """Update job definition with new image tag and vCPUs, return new revision ARN."""
    try:
        response = batch_client.register_job_definition(
            jobDefinitionName=job_def_name,
            type='container',
            containerProperties={
                'image': f'136132056804.dkr.ecr.us-east-1.amazonaws.com/bullseye-polygon-processor:{image_tag}',
                'jobRoleArn': 'arn:aws:iam::136132056804:role/BatchJobExecutionRole',
                'vcpus': vcpus,
                'memory': vcpus * 4096,
                'command': ['python', 'process_polygon.py', '--date', 'Ref::date', '--chunk-index', 'Ref::chunk-index'],
                'environment': [
                    {'name': 'DATE', 'value': 'Ref::date'},
                    {'name': 'CHUNK_INDEX', 'value': 'Ref::chunk-index'}
                ],
                'logConfiguration': {
                    'logDriver': 'awslogs',
                    'options': {
                        'awslogs-group': '/aws/batch/job',
                        'awslogs-region': 'us-east-1',
                        'awslogs-stream-prefix': 'bullseye-polygon-job'
                    }
                }
            }
        )
        job_def_arn = response['jobDefinitionArn']
        print(f"Registered job definition: {job_def_arn}")
        return job_def_arn
    except Exception as e:
        print(f"Failed to register job definition: {e}")
        return None

def submit_batch_job(batch_client, date_str, job_def_arn, chunk_index):
    """Submit Batch job for a single date and chunk index."""
    try:
        response = batch_client.submit_job(
            jobName=f'polygon-process-{date_str}-chunk-{chunk_index}',
            jobQueue='bullseye-queue',
            jobDefinition=job_def_arn,
            parameters={'date': date_str, 'chunk-index': str(chunk_index)},
            retryStrategy={'attempts': 3}  # Handle spot interruptions
        )
        job_id = response['jobId']
        print(f"Submitted job for {date_str} with chunk_index {chunk_index}: {job_id}")
        return job_id
    except Exception as e:
        print(f"Failed to submit job for {date_str}, chunk {chunk_index}: {e}")
        return None

def poll_job_status(batch_client, job_id):
    """Poll Batch job status until completion."""
    while True:
        response = batch_client.describe_jobs(jobs=[job_id])
        status = response['jobs'][0]['status']
        if status in ['SUCCEEDED', 'FAILED']:
            print(f"Job {job_id} status: {status}")
            return status == 'SUCCEEDED'
        time.sleep(30)

def main():
    parser = argparse.ArgumentParser(description='Invoke AWS Batch for Polygon data processing')
    parser.add_argument('--start-date', default=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', default=(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--image-tag', default='2025-08-10-chunked', help='ECR image tag')
    parser.add_argument('--profile', default='bullseye-batch-submitter', help='AWS CLI profile')
    parser.add_argument('--vcpus', type=int, default=4, help='Number of vCPUs for the job')
    parser.add_argument('--num-chunks', type=int, default=4, help='Number of chunks to split compressed intervals into')
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile)
    batch_client = session.client('batch')
    s3_client = session.client('s3')

    # Connect to DuckDB
    con = duckdb.connect(str(full_db_path))
    print(f"Connected to DuckDB database: {full_db_path}")

    dates = generate_date_list(args.start_date, args.end_date)
    for date_str in dates:
        # Compress intervals
        compressed = compress_intervals(con, 'raw_data', date_str)
        print(f"Generated {len(compressed)} compressed intervals for {date_str}")

        # Save to S3 as chunks
        save_compressed_intervals_to_s3(s3_client, TARGET_S3_BUCKET, date_str, compressed, args.num_chunks)

        # Update job definition
        job_def_arn = update_job_definition(batch_client, 'bullseye-polygon-job', args.image_tag, args.vcpus)
        if not job_def_arn:
            print("Aborting due to job definition failure")
            continue

        # Submit jobs for chunks in parallel
        with ThreadPoolExecutor(max_workers=args.num_chunks) as executor:
            futures = [executor.submit(submit_batch_job, batch_client, date_str, job_def_arn, chunk_index)
                       for chunk_index in range(args.num_chunks)]
            job_ids = [future.result() for future in as_completed(futures)]

        # Poll all jobs
        for job_id in job_ids:
            if job_id:
                success = poll_job_status(batch_client, job_id)
                if not success:
                    print(f"Job failed for job ID {job_id}, continuing...")

    con.close()

if __name__ == '__main__':
    main()