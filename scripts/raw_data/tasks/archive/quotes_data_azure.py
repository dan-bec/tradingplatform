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

import scripts.raw_data.config as config  # Adapt to your config module
import argparse
import os
from datetime import datetime, timedelta
import time
import gc
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.compute import ClusterSpec
from databricks.sdk.service.jobs import Job, NotebookTask
import duckdb

# Configuration
AZURE_ACCOUNT_URL = "https://bullseyestorage.blob.core.windows.net"  # Replace with your Azure storage account URL
AZURE_CONTAINER = "data-prep"  # Blob container for outputs
FULL_DB_PATH = config.FULL_DB_PATH  # Local DuckDB path
RAW_SCHEMA = config.RAW_SCHEMA  # e.g., 'raw_data'
DATABRICKS_NOTEBOOK_PATH = "/Users/<your-email>/polygon-etl-notebook"  # Path to Databricks notebook
options_quotes_dir = config.OPTION_QUOTES_DIR
options_quotes_dir.mkdir(parents=True, exist_ok=True)

def download_from_blob(blob_name, local_path):
    """Download from Azure Blob to local."""
    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(AZURE_ACCOUNT_URL, credential=credential)
    blob_client = blob_service.get_blob_client(AZURE_CONTAINER, blob_name)
    with open(local_path, "wb") as file:
        file.write(blob_client.download_blob().readall())
    print(f"Downloaded Blob {blob_name} to {local_path}")

def generate_date_list(start, end):
    """Generate a list of dates between start and end (inclusive) as strings."""
    date_list = []
    current_date = start
    while current_date <= end:
        date_list.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)
    return date_list

def main(start_date, end_date):
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    dates = generate_date_list(start_dt, end_dt)

    for date in dates:
        process_date_str = date

        # Temp dir for output Parquet only
        output_parquet_local = options_quotes_dir / f"{process_date_str}.parquet"

        try:
            # Step 1: Launch Databricks cluster
            w = WorkspaceClient()

            # Cluster spec (optimized for 100GB+)
            cluster_spec = ClusterSpec(
                cluster_name=f"polygon-etl-{process_date_str}",
                spark_version="13.3.x-scala2.12",
                node_type_id="Standard_DS4_v2",
                driver_node_type_id="Standard_DS4_v2",
                autoscale={"min_workers": 6, "max_workers": 10},
                spark_conf={
                    "spark.sql.shuffle.partitions": "512",
                    "spark.sql.autoBroadcastJoinThreshold": "10000000000",
                    "spark.hadoop.fs.s3a.access.key": config.get_static_string(config.DATASERVICES_PATH, "AWS_ACCESS_KEY"),
                    "spark.hadoop.fs.s3a.secret.key": config.get_static_string(config.DATASERVICES_PATH, "AWS_SECRET_KEY"),
                    "spark.hadoop.fs.s3a.endpoint": "https://files.polygon.io"
                },
                autotermination_minutes=10,
                enable_photon=True,
                spark_node_aws_attributes={"is_spot": True},
                libraries=[{"maven": {"coordinates": "com.github.splittable:spark-gzip:1.0"}}]
            )
            cluster = w.clusters.create(cluster_spec=cluster_spec)
            cluster_id = cluster.cluster_id
            print(f"Created cluster: {cluster_id}")

            # Step 2: Create and run job with parameters
            job = w.jobs.create(
                name=f"polygon-etl-job-{process_date_str}",
                tasks=[{
                    "task_key": "polygon-etl-task",
                    "existing_cluster_id": cluster_id,
                    "notebook_task": {
                        "notebook_path": DATABRICKS_NOTEBOOK_PATH,
                        "base_parameters": {
                            "date_str": process_date_str,
                            "output_path": f"abfss://{AZURE_CONTAINER}@bullseyestorage.dfs.core.windows.net/output/{process_date_str}_reduced_quotes.parquet"
                        }
                    }
                }]
            )
            run = w.jobs.run_now(job_id=job.job_id)
            run_id = run.run_id

            # Poll for job completion
            while True:
                status = w.jobs.get_run(run_id).state.life_cycle_state
                if status in ["TERMINATED", "SKIPPED", "INTERNAL_ERROR"]:
                    break
                time.sleep(30)
            print("Databricks job completed.")

            # Clean up cluster
            w.clusters.delete(cluster_id=cluster_id)
            print(f"Deleted cluster: {cluster_id}")

            # Step 3: Download Parquet from Blob
            output_blob = f"output/{process_date_str}_reduced_quotes.parquet"
            download_from_blob(output_blob, output_parquet_local)

            # Step 4: Import Parquet into local DuckDB
            con = duckdb.connect(str(FULL_DB_PATH))
            con.execute(f"""
                CREATE TABLE IF NOT EXISTS {RAW_SCHEMA}.option_quotes AS
                SELECT * FROM read_parquet('{output_parquet_local}')
            """)
            con.execute(f"""
                INSERT INTO {RAW_SCHEMA}.option_quotes
                SELECT * FROM read_parquet('{output_parquet_local}')
            """)
            print(f"Loaded {output_parquet_local} into {RAW_SCHEMA}.option_quotes")
            con.close()

        except Exception as e:
            print(f"Error in processing {process_date_str}: {e}")
        finally:
            # Clean up local files
            if output_parquet_local.exists():
                os.remove(output_parquet_local)
            gc.collect()

    end_time = time.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, default=config.START_DATE)
    parser.add_argument("--end-date", type=str, default=config.END_DATE)
    args = parser.parse_args()

    main(args.start_date, args.end_date)