import sys
from pathlib import Path

# Determine the project root dynamically
PROJECT_ROOT = Path(__file__).parent

# Insert the project root into sys.path if not already present
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import multiprocessing
from raw_data import main as run_raw_data
from unusual_baselining import main as run_unusual_baselining

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

if __name__ == "__main__":
    main()