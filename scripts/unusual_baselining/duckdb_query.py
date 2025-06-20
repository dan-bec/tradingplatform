import config as config
from datetime import datetime, date, timedelta
from pathlib import Path
import time
import duckdb
import pandas as pd
from tabulate import tabulate
import sys

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Define file paths
data_path = config.DATA_PATH
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
prep_schema = config.PREP_SCHEMA
compiled_schema = config.COMPILED_SCHEMA
itm_threshold = config.ITM_THRESHOLD
itm_threshold_100 = config.itm_str_prep(itm_threshold)
number_of_bins = config.NUMBER_OF_BINS
min_trade_value = config.MIN_TRADE_VALUE
expiration_days_out = config.EXPIRATION_DAYS_OUT
otm_range = config.STRICT_OTM

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
select * from
{prep_schema}.unusual_baselines
where security in ('MRK','ABBV','MSTR','AAPL','BK','CMA','FCNCA','GS','AMGN','LLY','TSLA','NVDA','BAC','GME','PLTR','PFE')
order by security   

select min_trade_value, expiration_days_out, otm_range, number_of_bins, max(data_date) as data_date from {prep_schema}.filtered_short_term_otm_options_trades group by 1,2,3,4;

select data_date,security, sector, industry, option_ticker, option_type, expiration,strike_price, option_condition_name, final_cluster, trade_value, trade_value_category, option_type, category_minimum, categiry_maximum
from {compiled_schema}.all_options_trades_above_baseline_{itm_threshold_100} 
where data_date > current_date() - INTERVAL 7 DAYS
'''

# Get unique rows from query
result = con.execute(f"""
            WITH _trade_prep AS (
                SELECT atd.*
                    , {min_trade_value} as min_trade_value
                    , {expiration_days_out} as expiration_days_out
                    , {otm_range} as otm_range
                    , occ.name as option_condition_name
                    , si.sector
                    , si.industry
                    , std.open as securty_open
                    , std.high as security_high
                    , std.low as security_low
                    , std.close as security_close
                    , row_number() OVER (PARTITION BY atd.security ORDER BY trade_value DESC) AS trade_rank
                    , log10(trade_value) AS trade_value_log10
                FROM {raw_schema}.all_options_trades_data atd
                JOIN {raw_schema}.option_condition_codes occ ON occ.id = atd.conditions
                JOIN {raw_schema}.sector_industry si ON si.security = atd.security
                JOIN {raw_schema}.stock_daily_data std ON std.security = atd.security AND std.data_date = atd.data_date
                WHERE 1=1
                    and atd.security = 'ABBV'
                    AND atd.conditions >= 209 -- Filters out Late, Canceled trades
                    AND atd.conditions < 248 -- Filters out after market trading
                    AND NOT (si.sector = 'Finance' and si.industry = 'Financial - Investment Funds')
                    AND atd.expiration > atd.data_date -- Options Purchased before Expiration
                    AND atd.expiration <= atd.data_date + INTERVAL {expiration_days_out}  DAYS -- Options Expiring in N days
                    AND atd.trade_value > {min_trade_value} -- minmum contract size of N
                    AND (
                        ({otm_range} != {True} AND ((atd.option_type = 'C' AND atd.strike_price > security_low)  OR (atd.option_type = 'P' AND atd.strike_price < security_high))) -- LOOSE: PARTIALLY OTM FOR DAY
                        OR ({otm_range} AND ((atd.option_type = 'C' AND atd.strike_price > security_high) OR (atd.option_type = 'P' AND atd.strike_price < security_low ))) -- STRICT: FULLY OTM FOR DAY
                        )
            )
            , _unique_qualifying_options AS (
                SELECT security,option_ticker,data_date,expiration
                FROM _trade_prep tp
                GROUP BY 1,2,3,4
            )
            , _determine_next_day AS (
                 SELECT data_date
                    , lead(data_date) over (order by data_date) as next_trading_day
                FROM {raw_schema}.stock_daily_data
                group by data_date
            )

                SELECT uqo.security
                    , uqo.option_ticker
                    , uqo.data_date
                    , uqo.expiration
                    , max(CASE WHEN sdd.data_date = dnd.next_trading_day THEN sdd.high END) as high_next_trading_date
                    , min(CASE WHEN sdd.data_date = dnd.next_trading_day THEN sdd.low  END) as low_next_trading_date
                    , max(CASE WHEN sdd.data_date > uqo.data_date THEN sdd.high END) as high_during_period
                    , min(CASE WHEN sdd.data_date > uqo.data_date THEN sdd.low  END) as low_during_period
                    , max(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.high END) as high_expiration
                    , min(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.low  END) as low_expiration
                    , min(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.close  END) as close_expiration
                FROM _unique_qualifying_options uqo
                JOIN _determine_next_day dnd on dnd.data_date = uqo.data_date
                LEFT JOIN {raw_schema}.stock_daily_data sdd ON sdd.security = uqo.security and sdd.data_date > uqo.data_date and sdd.data_date <= uqo.expiration
                GROUP BY 1,2,3,4
                limit 100
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