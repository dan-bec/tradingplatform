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

### SETTINGS ###

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Define file paths
data_path = 'data'
full_db_path = Path(f"{data_path}/master_database.db")
prep_schema = 'prep'
output_dir = Path(f"/projects/{prep_schema}/outputs")
otm_range = True
min_trade_value = 3_000
top_trades = 10_000
expiration_days_out = 30
custom_range_filter = .9
number_of_bins = 20

# Connect to DuckDB
con = duckdb.connect(str(full_db_path))
print(f"Connected to DuckDB database: {full_db_path}")

con.execute(f"DROP SCHEMA IF EXISTS {prep_schema} CASCADE;")
con.execute(f"CREATE SCHEMA {prep_schema};")
print(f"CREATE OR REPLACE SCHEMA {prep_schema};")

# Create trades_data table with only the relevant trades
con.execute(f"""
    CREATE OR REPLACE TABLE {prep_schema}.filtered_short_term_otm_options_trades AS
    WITH _trade_prep AS (
        SELECT atd.*
            , occ.name as option_condition_name
            , si.sector
            , si.industry
            , std.open as security_open
            , std.high as security_high
            , std.low as security_low
            , std.close as security_close
            , row_number() OVER (PARTITION BY atd.security ORDER BY trade_value DESC) AS trade_rank
            , log10(trade_value) AS trade_value_log10
        FROM raw_data.all_options_trades_data atd
        JOIN raw_data.option_condition_codes occ ON occ.id = atd.conditions
        JOIN raw_data.sector_industry si ON si.security = atd.security
        JOIN raw_data.stock_daily_data std ON std.security = atd.security AND std.data_date = atd.data_date
        WHERE 1=1
            AND atd.conditions >= 209 -- Filters out Late, Canceled trades
            AND atd.conditions < 248 -- Filters out after market trading
            AND NOT (si.sector = 'Finance' and si.industry = 'Financial - Investment Funds')
            AND atd.expiration > atd.data_date -- Options Purchased before Expiration
            AND atd.expiration <= atd.data_date + INTERVAL {expiration_days_out}  DAYS -- Options Expiring in N days
            AND atd.trade_value > {min_trade_value} -- minmum contract size of N
            AND (
                ('{otm_range}' != TRUE AND ((atd.option_type = 'C' AND atd.strike_price > security_low)  OR (atd.option_type = 'P' AND atd.strike_price < security_high))) -- LOOSE: PARTIALLY OTM FOR DAY
                OR ('{otm_range}'  = TRUE AND ((atd.option_type = 'C' AND atd.strike_price > security_high) OR (atd.option_type = 'P' AND atd.strike_price < security_low ))) -- STRICT: FULLY OTM FOR DAY
                )
    )
    , _unique_qualifying_options AS (
        SELECT security,option_ticker,data_date,expiration
        FROM _trade_prep tp
        GROUP BY 1,2,3,4
    )
    , _security_prices AS (
        SELECT uqo.security
            , uqo.option_ticker
            , uqo.data_date
            , uqo.expiration
            , max(CASE WHEN sdd.data_date > uqo.data_date THEN sdd.high END) as high_during_period
            , min(CASE WHEN sdd.data_date > uqo.data_date THEN sdd.low  END) as low_during_period
            , max(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.high END) as high_expiration
            , min(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.low  END) as low_expiration
            , min(CASE WHEN sdd.data_date = uqo.expiration THEN sdd.close  END) as close_expiration
        FROM _unique_qualifying_options uqo
        LEFT JOIN raw_data.stock_daily_data sdd ON sdd.security = uqo.security and sdd.data_date > uqo.data_date and sdd.data_date <= uqo.expiration
        GROUP BY 1,2,3,4
    )

    SELECT tp.*
    , ntile({number_of_bins}) OVER (PARTITION BY tp.security ORDER BY tp.trade_value desc) as trade_value_bin
    , CASE 
        WHEN tp.option_type = 'C' and strike_price <= high_during_period THEN 1
        WHEN tp.option_type = 'P' and strike_price >= low_during_period  THEN 1
        ELSE 0 
        END as itm
    , CASE 
        WHEN tp.option_type = 'C' and strike_price <= high_expiration THEN 1
        WHEN tp.option_type = 'P' and strike_price >= low_expiration  THEN 1
        ELSE 0 
        END as itm_expiration_day
    , CASE 
        WHEN tp.option_type = 'C' and strike_price <= close_expiration THEN 1
        WHEN tp.option_type = 'P' and strike_price >= close_expiration THEN 1
        ELSE 0 
        END as itm_expriation_close
    , CASE 
        WHEN tp.option_type = 'C' and strike_price > high_during_period THEN 1
        WHEN tp.option_type = 'P' and strike_price < low_during_period  THEN 1
        ELSE 0 
        END as otm
    FROM _trade_prep tp
    JOIN _security_prices sp on tp.security = sp.security and tp.option_ticker = sp.option_ticker and tp.data_date = sp.data_date
    -- WHERE trade_rank <= {top_trades} -- top N trades matching the previous filtering criteria
    ORDER BY tp.security, tp.option_ticker, tp.data_date
""")
print(f"!!!ROWS IN {prep_schema}.filtered_short_term_otm_options_trades!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.filtered_short_term_otm_options_trades").fetchone()[0]) # type: ignore

# Explicitly close the connection
con.close()

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")
