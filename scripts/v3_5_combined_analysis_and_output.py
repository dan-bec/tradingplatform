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
import numpy as np
from collections import defaultdict

### SETTINGS ###
data_path = Path(f"./data")
projects_path = Path(f"./projects")
full_db_path = Path(f"{data_path}/master_database.db")
prep_schema = 'prep'
compiled_schema = 'compiled'
output_dir = Path(f"{projects_path}/{compiled_schema}/outputs")
output_dir.mkdir(parents=True, exist_ok=True)
itm_threshold = 0.55  # Target ITM rate

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Connect to DuckDB
con = duckdb.connect(full_db_path)

con.execute(f"DROP SCHEMA IF EXISTS {compiled_schema} CASCADE;")
con.execute(f"CREATE SCHEMA {compiled_schema};")
print(f"CREATE OR REPLACE SCHEMA {compiled_schema};")

# Combine Prep Analysis
con.execute(f"""
    CREATE OR REPLACE TABLE {compiled_schema}.all_securities_stats AS
    SELECT si.security, si.sector, si.industry
    , {itm_threshold} as itm_threshold
    , ub.unusual_baseline
    , ub.trade_value_category
    , ub.number_of_trades as num_trades_over_baseline
    , sp.qualifying_trades as num_trades_total
    , cs.final_cluster
    , cs.trade_volume_bin
    , cs.cluster
    , sp.p90_trade_value
    , sp.p95_trade_value
    , sp.p99_trade_value
    , sp.p999_trade_value
    , sp.p9999_trade_value
    , sp.p99999_trade_value
    , sp.p999999_trade_value
    FROM raw_data.sector_industry si
    JOIN {prep_schema}.unusual_baselines ub on ub.security = si.security
    JOIN {prep_schema}.security_percentiles sp on sp.security = si.security
    JOIN {prep_schema}.clustered_securities cs on cs.security = si.security
    ORDER BY si.security
""")
print(f"Created and Loaded {compiled_schema}.all_securities_stats db table")
print(f"!!!ROWS IN {compiled_schema}.all_securities_stats!!!:", con.execute(f"SELECT COUNT(*) FROM {compiled_schema}.all_securities_stats").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
all_stats_output = Path(f"{output_dir}/all_securities_stats.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {compiled_schema}.all_securities_stats
        ORDER BY security
    ) TO '{all_stats_output}' (HEADER, DELIMITER ',')
""")
print(f"All securities stats data written to {all_stats_output}")

# Combine Prep Analysis for trade categories
con.execute(f"""
    CREATE OR REPLACE TABLE {compiled_schema}.all_securities_trade_value_category AS
    SELECT si.security, si.sector, si.industry
    , cs.final_cluster
    , cs.trade_volume_bin
    , cs.cluster
    , ip.trade_value_category
    , ip.max_trade_value
    , ip.min_trade_value
    , ip.itm_total,total
    , ip.itm_pct
    , {itm_threshold} as itm_threshold
    , CASE WHEN ub.security is not null THEN '1. ABOVE BASELINE' ELSE '2. BELOW BASELINE' END as ab
    , ip.itm_running_total
    , ip.running_total
    , ip.itm_running_pct
    FROM raw_data.sector_industry si
    JOIN {prep_schema}.itm_percentages ip on ip.security = si.security
    JOIN {prep_schema}.clustered_securities cs on cs.security = si.security
    LEFT JOIN {prep_schema}.unusual_baselines ub on ub.security = si.security and ip.min_trade_value >= ub.unusual_baseline
    ORDER BY si.security,ip.trade_value_category
""")
print(f"Created and Loaded {compiled_schema}.all_securities_trade_value_category db table")
print(f"!!!ROWS IN {compiled_schema}.all_securities_trade_value_category!!!:", con.execute(f"SELECT COUNT(*) FROM {compiled_schema}.all_securities_trade_value_category").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
all_trade_categories_output = Path(f"{output_dir}/all_securities_trade_value_category.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {compiled_schema}.all_securities_trade_value_category
        ORDER BY security
    ) TO '{all_trade_categories_output}' (HEADER, DELIMITER ',')
""")
print(f"All securities trade value categories stats data written to {all_trade_categories_output}")

# Combine Prep Analysis for trade categories
con.execute(f"""
    CREATE OR REPLACE TABLE {compiled_schema}.all_options_trades_above_baseline AS
    SELECT  si.security, si.sector, si.industry
    , cs.final_cluster
    , cs.trade_volume_bin
    , cs.cluster
    , ip.trade_value_category
    , ip.min_trade_value as category_minimum
    , ip.max_trade_value as categiry_maximum
    , fstoot.*
    FROM raw_data.sector_industry si
    JOIN {prep_schema}.filtered_short_term_otm_options_trades fstoot on fstoot.security = si.security
    JOIN {prep_schema}.unusual_baselines ub on ub.security = si.security and fstoot.trade_value >= ub.unusual_baseline
    JOIN {prep_schema}.clustered_securities cs on cs.security = si.security
    JOIN {prep_schema}.itm_percentages ip on ip.security = si.security and fstoot.trade_value >= ip.min_trade_value and fstoot.trade_value <= ip.max_trade_value
    ORDER BY fstoot.security, fstoot.data_date, fstoot.expiration, fstoot.option_ticker
""")
print(f"Created and Loaded {compiled_schema}.all_options_trades_above_baseline db table")
print(f"!!!ROWS IN {compiled_schema}.all_options_trades_above_baseline!!!:", con.execute(f"SELECT COUNT(*) FROM {compiled_schema}.all_options_trades_above_baseline").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
all_trade_categories_output = Path(f"{output_dir}/all_options_trades_above_baseline.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {compiled_schema}.all_options_trades_above_baseline
        ORDER BY security
    ) TO '{all_trade_categories_output}' (HEADER, DELIMITER ',')
""")
print(f"All options trades above baseline written to {all_trade_categories_output}")

### SEGMENTED OUTPUTS ###

# Create segmented outputs
segmented_dir = Path(f"{projects_path}/segmented")
segmented_dir.mkdir(parents=True, exist_ok=True)

# Function to modify sector name
def modify_sector_name(sector):
    return sector.lower().replace(' ', '_').replace('-', '_')

# Function to process industry name
def process_industry(industry):
    parts = industry.split('-', 1)
    processed = parts[0].strip().lower()
    return processed

# Get all unique sectors
sectors = con.execute("SELECT DISTINCT sector FROM raw_data.sector_industry").fetchall()
sectors = [row[0] for row in sectors]

for sector in sectors:
    modified_sector = modify_sector_name(sector)
    sector_folder = segmented_dir / modified_sector
    sector_folder.mkdir(parents=True, exist_ok=True)
    
    # Generate sector-level outputs
    for table, descriptor in [
        ('all_securities_stats', 'stats'),
        ('all_securities_trade_value_category', 'trade_value_category'),
        ('all_options_trades_above_baseline', 'trades_above_baseline')
    ]:
        query = f"SELECT * FROM {compiled_schema}.{table} WHERE sector = ?"
        df = con.execute(query, [sector]).fetchdf()
        if not df.empty:
            file_name = f"{modified_sector}_{descriptor}.csv"
            file_path = sector_folder / file_name
            df.to_csv(file_path, index=False)
            print(f"File written: {file_path}")
    
    # Get industries for this sector
    industries = con.execute("SELECT DISTINCT industry FROM raw_data.sector_industry WHERE sector = ?", [sector]).fetchall()
    industries = [row[0] for row in industries]
    
    # Group industries by processed name
    processed_to_industries = defaultdict(list)
    for industry in industries:
        processed = process_industry(industry)
        processed_to_industries[processed].append(industry)
    
    for processed_industry, industry_list in processed_to_industries.items():
        industry_folder = sector_folder / processed_industry
        industry_folder.mkdir(parents=True, exist_ok=True)
        
        # Generate industry-level outputs
        for table, descriptor in [
            ('all_securities_stats', 'stats'),
            ('all_securities_trade_value_category', 'trade_value_category'),
            ('all_options_trades_above_baseline', 'trades_above_baseline')
        ]:
            query = f"SELECT * FROM {compiled_schema}.{table} WHERE sector = ? AND industry IN ({','.join(['?' for _ in industry_list])})"
            params = [sector] + industry_list
            df = con.execute(query, params).fetchdf()
            if not df.empty:
                file_name = f"{modified_sector}_{processed_industry}_{descriptor}.csv"
                file_path = industry_folder / file_name
                df.to_csv(file_path, index=False)
                print(f"File written: {file_path}")
        
        # Get distinct trade_volume_bins for this sector and industry list
        query = f"SELECT DISTINCT trade_volume_bin FROM {compiled_schema}.all_securities_stats WHERE sector = ? AND industry IN ({','.join(['?' for _ in industry_list])})"
        params = [sector] + industry_list
        trade_volume_bins = con.execute(query, params).fetchall()
        trade_volume_bins = [row[0] for row in trade_volume_bins]
        
        # Generate trade_volume_bin-level outputs only for existing trade_volume_bins
        for trade_volume_bin in trade_volume_bins:
            tvb_folder = industry_folder / str(trade_volume_bin)
            tvb_folder.mkdir(parents=True, exist_ok=True)
            
            for table, descriptor in [
                ('all_securities_stats', 'stats'),
                ('all_securities_trade_value_category', 'trade_value_category'),
                ('all_options_trades_above_baseline', 'trades_above_baseline')
            ]:
                query = f"SELECT * FROM {compiled_schema}.{table} WHERE sector = ? AND industry IN ({','.join(['?' for _ in industry_list])}) AND trade_volume_bin = ?"
                params = [sector] + industry_list + [trade_volume_bin]
                df = con.execute(query, params).fetchdf()
                if not df.empty:
                    file_name = f"{modified_sector}_{processed_industry}_{trade_volume_bin}_{descriptor}.csv"
                    file_path = tvb_folder / file_name
                    df.to_csv(file_path, index=False)
                    print(f"File written: {file_path}")

# Close connection
con.close()

# Print execution time
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")