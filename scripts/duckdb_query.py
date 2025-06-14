import config
from datetime import datetime, date, timedelta
from pathlib import Path
import time
import duckdb
import pandas as pd
from tabulate import tabulate

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Define file paths
data_path = config.DATA_PATH
full_db_path = config.FULL_DB_PATH
prep_schema = config.PREP
compiled_schema = config.COMPILED

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

 {prep_schema}.security_percentiles
where security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR')
order by sector, industry, security

select * from
{prep_schema}.clustered_securities 
WHERE security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR')
order by cluster, num_trades desc
limit 100

select * from
 {prep_schema}.clustered_securities
where security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR')
order by security


select * from
{prep_schema}.itm_percentages
where security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR','PFE')
order by security, trade_value_category

select * from information_schema.columns
    order by table_schema, table_name, ordinal_position
    
select * from
{prep_schema}.unusual_baselines
where security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR','PFE')
order by security

select sector, industry, count(*)
                     from raw_data.sector_industry
                     group by 1,2
                     order by 1,2
'''

# Get unique rows from query
result = con.execute(f"""
select * from
{prep_schema}.unusual_baselines
where security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR','PFE')
order by security
""").fetchdf()
print(tabulate(result, headers='keys', tablefmt='psql')) # type: ignore
# result.to_csv(sys.stdout, index=False)


# Explicitly close the connection
con.close()

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")