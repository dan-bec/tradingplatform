import multiprocessing
import subprocess
from raw_data.main import main as run_raw_data
from unusual_baselining.main import main as run_unusual_baselining
import config
import upload_to_drive as upload_to_drive
import logging
from datetime import datetime

def push_to_github():
    repo_root = config.REPO_ROOT
    try:
        # Add all changes
        result = subprocess.run(["git", "-C", repo_root, "add", "."], check=True, capture_output=True, text=True)
        print(f"Git add output: {result.stdout}")
        
        # Check if there are changes to commit
        status = subprocess.run(["git", "-C", repo_root, "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout:
            print("No changes to commit.")
            return
        
        # Commit changes
        commit_message = f"Update outputs {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        result = subprocess.run(["git", "-C", repo_root, "commit", "-m", commit_message], check=True, capture_output=True, text=True)
        print(f"Git commit output: {result.stdout}")
        
        # Push to remote
        result = subprocess.run(["git", "-C", repo_root, "push", "origin", "main"], check=True, capture_output=True, text=True)
        print(f"Git push output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e.cmd}")
        print(f"Error output: {e.stderr}")
        raise

def push_to_drive():
    # Authenticate with Google Drive
    service = upload_to_drive.authenticate_google_drive(config.GDRIVE_CREDS)
    if service is None:
        logging.error("Failed to authenticate with Google Drive. Skipping upload.")
        return
    
    # Define target folder and create a date-based subfolder
    target_folder_id = "1ItSs-28eBoL1zGSKXwoKwnlHTZeQRcJQ"  # Replace with your folder ID
    date_folder_name = datetime.now().strftime("%Y-%m-%d")
    date_folder_id = upload_to_drive.create_folder(service, date_folder_name, target_folder_id)
    
    if date_folder_id is None:
        logging.error("Failed to create date folder. Skipping upload.")
        return
    
    # Proceed with upload (add your file upload logic here)
    logging.info(f"Created folder with ID: {date_folder_id}")

def main():
    # Run raw_data first (sequential)
    print("Starting raw_data execution...")
    run_raw_data()
    print("Completed raw_data execution.")

    # List of subsequent applications to run in parallel
    parallel_tasks = [
        run_unusual_baselining,
        # Add future applications here, e.g., run_other_app
    ]

    # Run subsequent tasks in parallel
    if parallel_tasks:
        processes = []
        for task in parallel_tasks:
            p = multiprocessing.Process(target=task)
            processes.append(p)
            p.start()
            print(f"Started {task.__name__} in parallel.")

        # Wait for all parallel tasks to complete
        for p in processes:
            p.join()
        print("All parallel tasks completed.")

    # push results to GitHub
    push_to_github()

    # push results to Google Drive
    # push_to_drive()

if __name__ == "__main__":
    main()