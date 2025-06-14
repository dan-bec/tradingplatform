import os
import duckdb
import re

# Define folders and corresponding PostgreSQL tables using absolute, platform-independent paths
base_dir = os.getcwd()  # Get the current working directory
folders_tables = [
    (os.path.join(base_dir, 'data', 'options', 'trades'), 'raw_data.polygon_options_trades'),
    (os.path.join(base_dir, 'data', 'options', 'daily'), 'raw_data.polygon_options_daily')
]

# Connect to DuckDB
con = duckdb.connect()

# Install and load the PostgreSQL extension
con.install_extension("postgres")
con.load_extension("postgres")

# Attach to the PostgreSQL database
# Replace 'youruser' and 'yourpass' with your actual PostgreSQL credentials
con.sql("ATTACH 'dbname=bullseye user=postgres password=XXD@FG3aga2WpEW6*aKAYPtbn host=localhost port=5432' AS pg (TYPE postgres);")

# Regular expression to match files named like 'YYYY-MM-DD.csv'
date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}\.csv')

# Process each folder
for folder, table in folders_tables:
    # Check if the folder exists
    if not os.path.exists(folder):
        print(f"Folder not found: {folder}")
        continue  # Skip to the next folder if the current one doesn’t exist

    # List and sort CSV files that match the date pattern
    files = [f for f in os.listdir(folder) if f.endswith('.csv') and date_pattern.match(f)]
    files.sort()  # Sort files by name (e.g., chronological order for YYYY-MM-DD)

    for file in files:
        filename = os.path.join(folder, file)
        date_str = file.split('.')[0]  # Extract date from filename (e.g., YYYY-MM-DD)
        print(f"Processing {filename} into {table}")
        # Insert CSV data into PostgreSQL with an additional file_date column
        con.sql(f"INSERT INTO pg.{table} SELECT '{date_str}' AS data_date, * FROM read_csv_auto('{filename}');")

# Close the DuckDB connection
con.close()