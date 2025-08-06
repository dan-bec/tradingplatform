import boto3
from datetime import datetime, timedelta
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def update_job_definition(batch_client, job_def_name, image_tag, num_workers):
    """Update job definition with new image tag and vCPUs, return new revision ARN."""
    try:
        response = batch_client.register_job_definition(
            jobDefinitionName=job_def_name,
            type='container',
            containerProperties={
                'image': f'136132056804.dkr.ecr.us-east-1.amazonaws.com/bullseye-polygon-processor:{image_tag}',
                'jobRoleArn': 'arn:aws:iam::136132056804:role/BatchJobExecutionRole',
                'vcpus': 4, 
                'memory': 4 * 4096,
                'command': ['python', 'process_polygon.py', '--date', 'Ref::date', '--num-workers', 'Ref::num-workers'],
                'environment': [
                    {'name': 'DATE', 'value': 'Ref::date'},
                    {'name': 'NUM_WORKERS', 'value': 'Ref::num-workers'}  # Fallback
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

def submit_batch_job(batch_client, date_str, job_def_arn, num_workers):
    """Submit Batch job for a single date using specified job definition."""
    try:
        response = batch_client.submit_job(
            jobName=f'polygon-process-{date_str}',
            jobQueue='bullseye-queue',
            jobDefinition=job_def_arn,
            parameters={'date': date_str, 'num-workers': str(num_workers)}
        )
        job_id = response['jobId']
        print(f"Submitted job for {date_str} with {num_workers} workers: {job_id}")
        return job_id
    except Exception as e:
        print(f"Failed to submit job for {date_str}: {e}")
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
    parser.add_argument('--image-tag', default='2025-08-04-001', help='ECR image tag')
    parser.add_argument('--profile', default='bullseye-batch-submitter', help='AWS CLI profile')
    parser.add_argument('--num-workers', type=int, default=4, help='Number of worker threads for downloads')
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile)
    batch_client = session.client('batch')

    # Update job definition with image tag and vCPUs
    job_def_arn = update_job_definition(batch_client, 'bullseye-polygon-job', args.image_tag, args.num_workers)
    if not job_def_arn:
        print("Aborting due to job definition failure")
        return

    dates = generate_date_list(args.start_date, args.end_date)
    # Submit jobs in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:  # Fixed for API stability
        futures = [executor.submit(submit_batch_job, batch_client, date_str, job_def_arn, args.num_workers)
                   for date_str in dates]
        job_ids = [future.result() for future in as_completed(futures)]

    # Poll all jobs
    for job_id in job_ids:
        if job_id:
            success = poll_job_status(batch_client, job_id)
            if not success:
                print(f"Job failed for job ID {job_id}, continuing...")

if __name__ == '__main__':
    main()