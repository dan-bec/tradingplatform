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
    
import scripts.unusual_baselining.config as config
import time
import duckdb
import pandas as pd
import numpy as np
from collections import defaultdict
import shutil

### SETTINGS ###
projects_path = config.PROJECTS_PATH
latest_dir = projects_path / "latest"
full_db_path = config.FULL_DB_PATH
raw_schema = config.RAW_SCHEMA
itm_path = config.ITM_PATH
prep_schema = config.PREP_SCHEMA
compiled_schema = config.COMPILED_SCHEMA
compiled_dir = config.COMPILED_OUTPUT_DIR
compiled_dir.mkdir(parents=True, exist_ok=True)

# Function to modify sector name
def modify_sector_name(sector):
    return sector.lower().replace(' ', '_').replace('-', '_')

# Function to process industry name
def process_industry(industry):
    parts = industry.split('-', 1)
    processed = parts[0].strip().lower().replace(' ', '_').replace('-', '_')
    return processed

def main(itm_threshold,number_of_bins):
    # Capture and print start time
    start_time = time.time()
    print(f"!!{FILE_NAME}!! Start time: {start_time:.2f} seconds")

    itm_threshold_100 = config.itm_str_prep(itm_threshold)
    # Connect to DuckDB
    con = duckdb.connect(full_db_path)
    print(f"Connected to DuckDB database: {full_db_path}")

    con.execute(f"CREATE SCHEMA IF NOT EXISTS {compiled_schema};")
    print(f"CREATE OR REPLACE SCHEMA {compiled_schema};")

    # Combine Prep Analysis
    con.execute(f"""
        CREATE OR REPLACE TABLE {compiled_schema}.all_securities_stats_{itm_threshold_100} AS
        SELECT si.security, si.sector, si.industry
        , {itm_threshold} as itm_threshold
        , ub.unusual_baseline
        , ub.trade_value_category
        , ub.number_of_trades as num_trades_over_baseline
        , sp.qualifying_trades as num_trades_total
        , cs.final_cluster
        , cs.trade_volume_bin
        , cs.trade_volume_bin_rank
        , cs.cluster
        , sp.p90_trade_value
        , sp.p95_trade_value
        , sp.p99_trade_value
        , sp.p999_trade_value
        , sp.p9999_trade_value
        , sp.p99999_trade_value
        , sp.p999999_trade_value
        FROM {raw_schema}.sector_industry si
        JOIN {prep_schema}.unusual_baselines_{itm_threshold_100} ub on ub.security = si.security
        JOIN {prep_schema}.security_percentiles sp on sp.security = si.security
        JOIN {prep_schema}.clustered_securities cs on cs.security = si.security
        ORDER BY si.security
    """)
    print(f"Created and Loaded {compiled_schema}.all_securities_stats_{itm_threshold_100}  db table")
    print(f"!!!ROWS IN {compiled_schema}.all_securities_stats_{itm_threshold_100} !!!:", con.execute(f"SELECT COUNT(*) FROM {compiled_schema}.all_securities_stats_{itm_threshold_100} ").fetchone()[0]) # type: ignore

    # Output {project}_percentiles files and baseline file
    all_stats_output = Path(f"{compiled_dir}/1_all_stats.csv")
    con.execute(f"""
        COPY (
            SELECT *
            FROM {compiled_schema}.all_securities_stats_{itm_threshold_100}
            WHERE trade_volume_bin_rank < {number_of_bins}
            ORDER BY security
        ) TO '{all_stats_output}' (HEADER, DELIMITER ',')
    """)
    print(f"All securities stats data written to {all_stats_output}")
    shutil.copy(all_stats_output, latest_dir / all_stats_output.name)
    print(f"All options trades above baseline written to {latest_dir}/{all_stats_output.name}")

    # Combine Prep Analysis for trade categories
    con.execute(f"""
        CREATE OR REPLACE TABLE {compiled_schema}.all_securities_trade_value_category_{itm_threshold_100}  AS
        SELECT si.security, si.sector, si.industry
        , cs.final_cluster
        , cs.trade_volume_bin
        , cs.trade_volume_bin_rank
        , cs.cluster
        , ip.trade_value_category
        , ip.max_trade_value
        , ip.min_trade_value
        , ip.itm_count
        , ip.total_count
        , ip.itm_pct
        , {itm_threshold} as itm_threshold
        , CASE WHEN ub.security is not null THEN '1. ABOVE BASELINE' ELSE '2. BELOW BASELINE' END as ab
        , ip.itm_running_total
        , ip.running_total
        , ip.itm_running_pct
        FROM {raw_schema}.sector_industry si
        JOIN {prep_schema}.itm_percentages ip on ip.security = si.security
        JOIN {prep_schema}.clustered_securities cs on cs.security = si.security
        LEFT JOIN {prep_schema}.unusual_baselines_{itm_threshold_100} ub on ub.security = si.security and ip.min_trade_value >= ub.unusual_baseline
        ORDER BY si.security,ip.trade_value_category
    """)
    print(f"Created and Loaded {compiled_schema}.all_securities_trade_value_category_{itm_threshold_100} db table")
    print(f"!!!ROWS IN {compiled_schema}.all_securities_trade_value_category_{itm_threshold_100}!!!:", con.execute(f"SELECT COUNT(*) FROM {compiled_schema}.all_securities_trade_value_category_{itm_threshold_100}").fetchone()[0]) # type: ignore

    # Output {project}_percentiles files and baseline file
    all_trade_categories_output = Path(f"{compiled_dir}/2_all_trade_value_categories.csv")
    con.execute(f"""
        COPY (
            SELECT *
            FROM {compiled_schema}.all_securities_trade_value_category_{itm_threshold_100}
            WHERE trade_volume_bin_rank < {number_of_bins}
            ORDER BY security
        ) TO '{all_trade_categories_output}' (HEADER, DELIMITER ',')
    """)
    print(f"All securities trade value categories stats data written to {all_trade_categories_output}")
    shutil.copy(all_trade_categories_output, latest_dir / all_trade_categories_output.name)
    print(f"All options trades above baseline written to {latest_dir}/{all_trade_categories_output.name}")

    # Combine Prep Analysis for trade categories
    con.execute(f"""
        CREATE OR REPLACE TABLE {compiled_schema}.all_options_trades_above_baseline_{itm_threshold_100} AS
        SELECT  si.security, si.sector, si.industry
        , cs.final_cluster
        , cs.trade_volume_bin
        , cs.trade_volume_bin_rank
        , cs.cluster
        , ip.trade_value_category
        , ip.min_trade_value as category_minimum
        , ip.max_trade_value as category_maximum
        , fstoot.*
        FROM {raw_schema}.sector_industry si
        JOIN {prep_schema}.filtered_short_term_otm_options_trades fstoot on fstoot.security = si.security
        JOIN {prep_schema}.unusual_baselines_{itm_threshold_100} ub on ub.security = si.security and fstoot.trade_value >= ub.unusual_baseline
        JOIN {prep_schema}.clustered_securities cs on cs.security = si.security
        JOIN {prep_schema}.itm_percentages ip on ip.security = si.security and fstoot.trade_value >= ip.min_trade_value and fstoot.trade_value <= ip.max_trade_value
        ORDER BY fstoot.security, fstoot.data_date, fstoot.expiration, fstoot.option_ticker
    """)
    print(f"Created and Loaded {compiled_schema}.all_options_trades_above_baseline_{itm_threshold_100} db table")
    print(f"!!!ROWS IN {compiled_schema}.all_options_trades_above_baseline_{itm_threshold_100}!!!:", con.execute(f"SELECT COUNT(*) FROM {compiled_schema}.all_options_trades_above_baseline_{itm_threshold_100}").fetchone()[0]) # type: ignore

    # Output {project}_percentiles files and baseline file
    all_trades_output = Path(f"{compiled_dir}/3_all_trades_above_baseline.csv")
    con.execute(f"""
        COPY (
            SELECT *
            FROM {compiled_schema}.all_options_trades_above_baseline_{itm_threshold_100}
            WHERE trade_volume_bin_rank < {number_of_bins}
            ORDER BY security
        ) TO '{all_trades_output}' (HEADER, DELIMITER ',')
    """)
    print(f"All options trades above baseline written to {all_trades_output}")
    shutil.copy(all_trades_output, latest_dir / all_trades_output.name)
    print(f"All options trades above baseline written to {latest_dir}/{all_trades_output.name}")

    ### SEGMENTED OUTPUTS ###

    # Create segmented outputs
    segmented_dir = config.SEGMENTED_OUTPUT_DIR
    segmented_dir.mkdir(parents=True, exist_ok=True)

    # Get all unique sectors
    sectors = con.execute(f"SELECT DISTINCT sector FROM {raw_schema}.sector_industry").fetchall()
    sectors = [row[0] for row in sectors]
 
    for sector in sectors:
        modified_sector = modify_sector_name(sector)
        sector_folder = segmented_dir / modified_sector
        sector_folder.mkdir(parents=True, exist_ok=True)
        
        # Generate sector-level outputs
        for table, descriptor in [
            (f'all_securities_stats_{itm_threshold_100}', '1_stats'),
            (f'all_securities_trade_value_category_{itm_threshold_100}', '2_trade_value_category'),
            (f'all_options_trades_above_baseline_{itm_threshold_100}', '3_trades_above_baseline')
        ]:
            query = f"SELECT * FROM {compiled_schema}.{table} WHERE trade_volume_bin_rank < {number_of_bins} AND sector = ?"
            df = con.execute(query, [sector]).fetchdf()
            if not df.empty:
                file_name = f"{modified_sector}__file_{descriptor}.csv"
                file_path = sector_folder / file_name
                df.to_csv(file_path, index=False)
                # print(f"File written: {file_path}")
        
        # Get industries for this sector
        industries = con.execute(f"SELECT DISTINCT industry FROM {raw_schema}.sector_industry WHERE sector = ?", [sector]).fetchall()
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
                (f'all_securities_stats_{itm_threshold_100}', '1_stats'),
                (f'all_securities_trade_value_category_{itm_threshold_100}', '2_trade_value_category'),
                (f'all_options_trades_above_baseline_{itm_threshold_100}', '3_trades_above_baseline')
            ]:
                query = f"SELECT * FROM {compiled_schema}.{table} WHERE trade_volume_bin_rank < {number_of_bins} AND sector = ? AND industry IN ({','.join(['?' for _ in industry_list])})"
                params = [sector] + industry_list
                df = con.execute(query, params).fetchdf()
                if not df.empty:
                    file_name = f"{modified_sector}_{processed_industry}__file_{descriptor}.csv"
                    file_path = industry_folder / file_name
                    df.to_csv(file_path, index=False)
                    # print(f"File written: {file_path}")
            
            # Get distinct trade_volume_bins for this sector and industry list
            query = f"SELECT DISTINCT trade_volume_bin_rank FROM {compiled_schema}.all_securities_stats_{itm_threshold_100} WHERE trade_volume_bin_rank < {number_of_bins} AND sector = ? AND industry IN ({','.join(['?' for _ in industry_list])})"
            params = [sector] + industry_list
            trade_volume_bins_rank = con.execute(query, params).fetchall()
            trade_volume_bins_rank = [row[0] for row in trade_volume_bins_rank]
            
            # Generate trade_volume_bin-level outputs only for existing trade_volume_bins_rank
            for trade_volume_bin_rank in trade_volume_bins_rank:
                tvb_folder = Path(str(industry_folder) + '/bin_' + str(trade_volume_bin_rank))
                tvb_folder.mkdir(parents=True, exist_ok=True)
                
                for table, descriptor in [
                    (f'all_securities_stats_{itm_threshold_100}', '1_stats'),
                    (f'all_securities_trade_value_category_{itm_threshold_100}', '2_trade_value_category'),
                    (f'all_options_trades_above_baseline_{itm_threshold_100}', '3_trades_above_baseline')
                ]:
                    query = f"SELECT * FROM {compiled_schema}.{table} WHERE trade_volume_bin_rank < {number_of_bins} AND sector = ? AND industry IN ({','.join(['?' for _ in industry_list])}) AND trade_volume_bin_rank = ?"
                    params = [sector] + industry_list + [trade_volume_bin_rank]
                    df = con.execute(query, params).fetchdf()
                    if not df.empty:
                        file_name = f"{modified_sector}_{processed_industry}__bin_{trade_volume_bin_rank}__file_{descriptor}.csv"
                        file_path = tvb_folder / file_name
                        df.to_csv(file_path, index=False)
                        # print(f"File written: {file_path}")
    print(f"Completed writing all segmented output files.")

    # Close connection
    con.close()

    # Print execution time
    end_time = time.time()
    print(f"!!{FILE_NAME}!! End time: {end_time:.2f} seconds")
    duration = end_time - start_time
    print(f"!!{FILE_NAME}!! Execution time: {duration:.2f} seconds")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--itm-threshold", type=float, default=config.ITM_THRESHOLD, help="ITM threshold")
    parser.add_argument("--number-of-bins", type=int, default=config.NUMBER_OF_BINS, help="Number of bins")
    args = parser.parse_args()

    main(args.itm_threshold,args.number_of_bins)