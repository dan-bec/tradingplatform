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
import duckdb
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import scipy.stats as stats

# Configuration
prep_schema = config.PREP_SCHEMA
db_path = config.FULL_DB_PATH
segmented_output = config.SEGMENTED_OUTPUT_DIR
prep_output = config.PREP_OUTPUT_DIR

def sanitize_name(name):
    """Sanitize a string to be used as a file or directory name."""
    return "".join(c for c in name if c.isalnum() or c in (' ', '_')).replace(' ', '_')

def linregress_zero_intercept(x, y):
    """Perform linear regression with intercept forced to zero."""
    x = np.array(x)
    y = np.array(y)
    if np.sum(x**2) == 0:
        m = np.nan
        r_squared = np.nan
        p_value = np.nan
        std_err = np.nan
    else:
        m = np.sum(x * y) / np.sum(x**2)
        y_pred = m * x
        residuals = y - y_pred
        n = len(x)
        if n > 1:
            var_m = np.sum(residuals**2) / (n - 1) / np.sum(x**2)
            std_err = np.sqrt(var_m)
            t_stat = m / std_err
            p_value = 2 * (1 - stats.t.cdf(np.abs(t_stat), df=n-1))
        else:
            std_err = np.nan
            p_value = np.nan
        r_value = np.corrcoef(x, y)[0,1] if n > 1 else np.nan
        r_squared = r_value ** 2 if not np.isnan(r_value) else np.nan
    return m, 0, r_squared, p_value, std_err

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

    # Close the initial database connection
    con.close()

    # Initialize lists to collect regression data
    industry_regression_data = []
    sector_regression_data = []

    # Generate charts for each industry, organized by sector
    for (sector, industry), group in df.groupby(['sector', 'industry']):
        safe_sector = sanitize_name(sector)
        safe_industry = sanitize_name(industry)
        
        # Create sector directory if it doesn’t exist
        sector_dir = segmented_output / safe_sector
        sector_dir.mkdir(parents=True, exist_ok=True)
        
        # Define output file path
        output_file = sector_dir / f"ipo_trend_{safe_industry}.png"
        
        # Calculate the number of unique tickers
        num_tickers = group['security'].nunique()
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        sns.lineplot(data=group, x='rn', y='pct_change', hue='security', marker='o', palette='tab10')
        
        # Perform linear regression with zero intercept
        rn_all = group['rn']
        pct_change_all = group['pct_change']
        slope, intercept, r_squared, p_value, std_err = linregress_zero_intercept(rn_all, pct_change_all)
        
        # Plot the regression line
        rn_range = np.array([min(rn_all), max(rn_all)])
        pct_pred = slope * rn_range + intercept  # intercept is 0
        plt.plot(rn_range, pct_pred, 'r-', label=f'Regression (slope={slope:.2f})', linewidth=2)
        
        # Customize the plot
        plt.legend(title='Security', bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.title(f"Sector: {sector} - Industry: {industry}\nNumber of Tickers: {num_tickers}\nRegression: Slope={slope:.2f}, Intercept={intercept:.2f}, R²={r_squared:.2f}", pad=20)
        plt.xlabel('Days Since IPO (rn)')
        plt.ylabel('Percentage Change from IPO Close (%)')
        plt.grid(True)
        
        # Save the plot to a file
        plt.savefig(output_file, bbox_inches='tight', dpi=300)
        plt.close()
        
        # Collect industry regression data
        industry_regression_data.append((
            days_since_ipo, sector, industry, slope, intercept, r_squared, p_value, std_err, num_tickers
        ))

    # Generate sector-level charts with lines per ticker and regression data
    for sector in df['sector'].unique():
        sector_group = df[df['sector'] == sector]
        num_industries = sector_group['industry'].nunique()
        num_tickers = sector_group['security'].nunique()
        
        # Perform sector-level regression with zero intercept
        rn_all = sector_group['rn']
        pct_change_all = sector_group['pct_change']
        slope_sector, intercept_sector, r_squared_sector, p_value_sector, std_err_sector = linregress_zero_intercept(rn_all, pct_change_all)
        
        # Plot the sector chart with lines per ticker
        plt.figure(figsize=(12, 8))
        sns.lineplot(data=sector_group, x='rn', y='pct_change', hue='security', alpha=0.3)
        rn_range = np.array([min(rn_all), max(rn_all)])
        pct_pred_sector = slope_sector * rn_range + intercept_sector  # intercept is 0
        plt.plot(rn_range, pct_pred_sector, 'k--', linewidth=2, label=f'Sector Overall (slope={slope_sector:.2f})')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', ncol=2)
        plt.title(f"Sector: {sector}\nIndividual Ticker Trends and Sector Regression\nNumber of Industries: {num_industries}, Number of Tickers: {num_tickers}")
        plt.xlabel('Days Since IPO (rn)')
        plt.ylabel('Percentage Change from IPO Close (%)')
        plt.grid(True)
        
        # Save the sector plot
        safe_sector = sanitize_name(sector)
        sector_dir = segmented_output / safe_sector
        sector_chart_file = sector_dir / f"{safe_sector}_sector_trend.png"
        plt.savefig(sector_chart_file, bbox_inches='tight', dpi=300)
        plt.close()
        
        # Collect sector regression data
        sector_regression_data.append((
            days_since_ipo, sector, slope_sector, intercept_sector, r_squared_sector,
            p_value_sector, std_err_sector, num_industries, num_tickers
        ))

    # Save regression results to DuckDB
    con = duckdb.connect(db_path)
    
    # Create or replace industry regression table
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {prep_schema}.industry_regression_results (
            days_since_ipo INTEGER,
            sector VARCHAR,
            industry VARCHAR,
            slope DOUBLE,
            intercept DOUBLE,
            r_squared DOUBLE,
            p_value DOUBLE,
            std_err DOUBLE,
            num_tickers INTEGER,
            PRIMARY KEY (days_since_ipo, sector, industry)
        )
    """)
    con.execute(f"DELETE FROM {prep_schema}.industry_regression_results WHERE days_since_ipo = ?", (days_since_ipo,))
    con.executemany(f"INSERT INTO {prep_schema}.industry_regression_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", industry_regression_data)
    
    # Create or replace sector regression table
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {prep_schema}.sector_regression_results (
            days_since_ipo INTEGER,
            sector VARCHAR,
            slope DOUBLE,
            intercept DOUBLE,
            r_squared DOUBLE,
            p_value DOUBLE,
            std_err DOUBLE,
            num_industries INTEGER,
            num_tickers INTEGER,
            PRIMARY KEY (days_since_ipo, sector)
        )
    """)
    con.execute(f"DELETE FROM {prep_schema}.sector_regression_results WHERE days_since_ipo = ?", (days_since_ipo,))
    con.executemany(f"INSERT INTO {prep_schema}.sector_regression_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", sector_regression_data)
    
    con.close()
    print(f"Saved {len(industry_regression_data)} industry and {len(sector_regression_data)} sector regression results to DuckDB.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-since-ipo", type=int, default=config.DAYS_SINCE_IPO, help="Number of days since IPO")
    args = parser.parse_args()

    main(args.days_since_ipo)