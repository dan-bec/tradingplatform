import os
import csv
import re
from datetime import datetime, date, timedelta
from pathlib import Path
import requests
import time
import duckdb
import sys
import subprocess
import pandas as pd
from tabulate import tabulate

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Define file paths
data_path = 'data'
full_db_path = Path(f"{data_path}/master_database.db")
project = 'banks'

# Connect to DuckDB
con = duckdb.connect(str(full_db_path))

'''
try:
    result = con.execute("DESCRIBE raw_data.all_trades_data").fetchall()
    print("Columns in raw_data.all_trades_data:")
    for row in result:
        print(row[0])
except duckdb.CatalogException:
    print("Table raw_data.all_trades_data does not exist.")

con.execute("ALTER TABLE raw_data.all_trades_data RENAME all_options_trades_data")

con.execute("DROP TABLE pharma.filtered_trade_data")

    SELECT distinct atd.security, atd.option_ticker, atd.data_date
    FROM raw_data.all_trades_data atd
    WHERE 
    ORDER BY 1
'''
# Get unique rows from query
result = con.execute(f"""
    SELECT security, trade_value_bracket, count(*), sum(count(*)) OVER (PARTITION BY security ORDER BY trade_value_bracket desc) running_count
    FROM  {project}.filtered_trade_data
    GROUP BY 1,2
    ORDER BY 1,2 desc
""").fetchdf()
print(tabulate(result, headers='keys', tablefmt='psql')) # type: ignore

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")

# Explicitly close the connection
con.close()

''' '''