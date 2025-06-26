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

import scripts.ipo_trends.config as config
import time
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import linregress
import numpy as np

# Configuration (adjust these values as needed)
prep_schema = config.PREP_SCHEMA  # Replace with your actual schema name
db_path = config.FULL_DB_PATH  # Replace with your DuckDB database file path
prep_output = config.PREP_OUTPUT_DIR

def sanitize_name(name):
    """Sanitize a string to be used as a file or directory name."""
    return "".join(c for c in name if c.isalnum() or c in (' ', '_')).replace(' ', '_')

def main(days_since_ipo):
    # Connect to the DuckDB database
    con = duckdb.connect(db_path)

    # SQL query to calculate percentage change, including sector
    query = f"""
    WITH ipo_closes AS (
        SELECT security, close AS ipo_close
        FROM {prep_schema}.ipos_first_{days_since_ipo}_days
        WHERE rn = 0
    )
    SELECT 
        a.security,
        a.rn,
        a.close,
        b.ipo_close,
        ((a.close - b.ipo_close) / b.ipo_close) * 100 AS pct_change,
        a.industry,
        a.sector
    FROM {prep_schema}.ipos_first_{days_since_ipo}_days a
    JOIN ipo_closes b ON a.security = b.security
    """

    # Fetch data into a pandas DataFrame
    df = con.execute(query).fetchdf()

    # Close the database connection
    con.close()

    # Generate charts for each industry, organized by sector
    for industry, group in df.groupby('industry'):
        # Extract sector from the group (assuming all rows in group have the same sector)
        sector = group['sector'].iloc[0]
        safe_sector = sanitize_name(sector)
        safe_industry = sanitize_name(industry)
        
        # Create sector directory if it doesn't exist
        sector_dir = prep_output / safe_sector
        sector_dir.mkdir(parents=True, exist_ok=True)
        
        # Define output file path
        output_file = sector_dir / f"ipo_trend_{safe_industry}.png"
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        sns.lineplot(data=group, x='rn', y='pct_change', hue='security', marker='o', palette='tab10')
        
        # Perform linear regression on all (rn, pct_change) points in the industry
        rn_all = group['rn']
        pct_change_all = group['pct_change']
        slope, intercept, r_value, p_value, std_err = linregress(rn_all, pct_change_all)
        
        # Plot the regression line
        rn_range = np.array([0, days_since_ipo])  # type: ignore
        pct_pred = slope * rn_range + intercept
        plt.plot(rn_range, pct_pred, 'k--', label='Regression Line', linewidth=2)
        
        # Customize the plot
        plt.legend(title='Security', bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.title(f"Sector: {sector} - Industry: {industry}\nRegression: Slope={slope:.2f}, Intercept={intercept:.2f}, R²={r_value**2:.2f}", pad=20)  # type: ignore
        plt.xlabel('Days Since IPO (rn)')
        plt.ylabel('Percentage Change from IPO Close (%)')
        plt.grid(True)
        
        # Save the plot to a file
        plt.savefig(output_file, bbox_inches='tight', dpi=300)
        plt.close()  # Close the figure to free memory

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-since-ipo", type=int, default=config.DAYS_SINCE_IPO, help="Number of days since IPO")
    args = parser.parse_args()

    main(args.days_since_ipo)