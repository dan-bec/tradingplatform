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
project = 'pharma'

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

SELECT 'DROP TABLE ' || table_schema || '.' || table_name || ';'
FROM information_schema.tables
where table_schema = 'pharma'

DROP TABLE pharma.filtered_option_trade_data;                       
DROP TABLE pharma.notable_options_trades;                           
DROP TABLE pharma.securities;                                       
DROP TABLE pharma.security_percentiles;                             
DROP TABLE pharma.successful_options_trades;                        
DROP TABLE pharma.targeted_options_trades;                          
DROP TABLE pharma._large_trades;  

 DROP TABLE banks.filtered_option_trade_data;                        
 DROP TABLE banks.securities;                                        
 DROP TABLE banks.security_percentiles;                              
 DROP TABLE banks._large_trades;    
'''
# Get unique rows from query
result = con.execute(f"""
select security,max(trade_date)
from pharma.notable_options_trades
where security = 'MRK'
group by 1
                     ;  
""").fetchdf()
print(tabulate(result, headers='keys', tablefmt='psql')) # type: ignore
# result.to_csv(sys.stdout, index=False)

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")

# Explicitly close the connection
con.close()

''' '''