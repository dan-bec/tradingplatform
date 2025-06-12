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
stock_summary_dir = Path(f"{data_path}/stocks/daily")
option_trade_dir = Path(f"{data_path}/options/trades")
num_files_to_load = 200
projects_path = 'projects'
project = 'banks'
securities_file = Path(f"{projects_path}/{project}/securities.csv")
output_dir = Path(f"{projects_path}/{project}/outputs")
min_trade_value = 3_000
# pharma = 10_000
# banks = 3_000
expiration_days_out = 30
custom_range_filter = .985
number_of_bins = 10

# Create output directory if it doesn’t exist
os.makedirs(output_dir, exist_ok=True)

'''
if full_db_path.exists():
    print("File exists, deleting...")
    full_db_path.unlink()
else:
    print("File does not exist at the specified path.")
'''

# Connect to DuckDB
con = duckdb.connect(str(full_db_path))

# Function to extract static string variables from DataServices.cs
def get_static_string(file_path, var_name):
    """Extracts a static string variable from a C# file."""
    try:
        with open(file_path, 'r') as file:
            content = file.read()
        pattern = rf'public static string {var_name} = "(.*?)";'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        else:
            raise ValueError(f"{var_name} not found in the file")
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {file_path} does not exist")
    except Exception as e:
        raise Exception(f"Error reading {var_name} from {file_path}: {e}")

# Set up API key (kept for condition codes fetching)
script_dir = os.path.dirname(os.path.abspath(__file__))
dataservices_path = os.path.join(script_dir, "..", "src", "BullseyeApp", "Shared", "Data", "DataService.cs")
API_KEY = get_static_string(dataservices_path, "API_KEY")


def get_files_to_load(src_tbl: str, directory_path: Path, num_files_to_load: int, db_connection: duckdb.DuckDBPyConnection) -> list[str]:
    """
    Retrieves file paths of CSV files in the specified directory that have not yet been loaded into the database.

    Args:
        directory_path (Path): Directory containing the CSV files.
        num_files_to_load (int): Maximum number of recent files to consider.
        db_connection (duckdb.DuckDBPyConnection): DuckDB database connection.

    Returns:
        list[str]: List of file paths (as strings) to be loaded.
    """
    # Find all CSV files in the directory
    all_files = list(directory_path.glob("*.csv"))
    valid_files = []
    for file in all_files:
        try:
            file_date = datetime.strptime(file.stem, "%Y-%m-%d").date()
            valid_files.append((file_date, file))
        except ValueError:
            continue

    if not valid_files:
        print("No valid data files found.")
        return []

    # Sort files by date descending
    valid_files.sort(key=lambda x: x[0], reverse=True)

    # Take the last N files
    last_n_files = valid_files[:num_files_to_load]

    # Get existing dates from the database
    try:
        existing_dates = set(row[0] for row in db_connection.execute(f"SELECT DISTINCT data_date FROM raw_data.{src_tbl}").fetchall())
    except duckdb.CatalogException:
        existing_dates = set()

    # Filter to get only new files
    files_to_load = [(date, file) for date, file in last_n_files if date not in existing_dates]
    file_paths = [str(file) for date, file in files_to_load]
    print(f"!!!TO BE LOADED!!!: {[str(file) for date, file in files_to_load]}")

    # Print latest and earliest dates if files exist
    if files_to_load:
        latest_date = files_to_load[0][0]
        earliest_date = files_to_load[-1][0]
        print(f"Latest date to load: {latest_date}")
        print(f"Earliest date to load: {earliest_date}")
    else:
        print("No new files to load, skipping date identification.")

    return file_paths

### RAW DATA ###

# Create trades_data table with only the relevant files
con.execute(f"CREATE SCHEMA IF NOT EXISTS raw_data")
print("CREATE SCHEMA IF NOT EXISTS raw_data")

#### CONDITIONS ####

# Fetch option condition codes from Polygon.io
condition_codes = []
url = "https://api.polygon.io/v3/reference/conditions"
params = {
    "asset_class": "options",
    "order": "asc",
    "limit": 1000,
    "sort": "id",
    "apiKey": API_KEY
}
first_request = True
while url:
    if first_request:
        response = requests.get(url, params=params)
        first_request = False
    else:
        response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        condition_codes.extend(data.get("results", []))
        url = data.get("next_url")
    else:
        print(f"Failed to fetch condition codes: {response.status_code}")
        break

# Create condition_codes table in DuckDB
if condition_codes:
    con.execute("""
        CREATE OR REPLACE TABLE raw_data.option_condition_codes (
            id INTEGER,
            type VARCHAR,
            name VARCHAR,
            asset_class VARCHAR,
            data_types VARCHAR
        )
    """)
    print("CREATE OR REPLACE TABLE raw_data.option_condition_codes")
    for code in condition_codes:
        data_types_str = ",".join(code.get("data_types", []))
        con.execute(
            "INSERT INTO raw_data.option_condition_codes (id, type, name, asset_class, data_types) VALUES (?, ?, ?, ?, ?)",
            (code.get("id"), code.get("type"), code.get("name"), code.get("asset_class"), data_types_str)
        )
    print("Condition codes fetched and stored in the database.")
else:
    print("No condition codes fetched.")

#### STOCK SUMMARY DATA ####

# Create trades_data table with only the relevant files
con.execute(f"""
    CREATE TABLE IF NOT EXISTS raw_data.stock_daily_data (
            security VARCHAR,
            volume BIGINT,
            open DOUBLE,
            close DOUBLE,
            high DOUBLE,
            low DOUBLE,
            window_start BIGINT,
            transactions BIGINT,
            data_date DATE,
            PRIMARY KEY (data_date, security)
        )
""")
print(f"Created raw_data.stock_daily_data db table")

stock_daily_files = get_files_to_load('stock_daily_data',stock_summary_dir, num_files_to_load, con)
# Load only the new files
if stock_daily_files:
    con.execute(f"""
        INSERT INTO raw_data.stock_daily_data
        SELECT 
            ticker,
            volume,
            open,
            close,
            high,
            low,
            window_start,
            transactions,
            CAST(
                CASE
                    WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1) != '' 
                    THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1)
                    ELSE NULL
                END AS DATE
            ) AS data_date
        FROM read_csv_auto({stock_daily_files}, filename=True)
    """)
    print(f"Loaded data from {len(stock_daily_files)} new files into raw_data.stock_daily_data")
else:
    print("No new data to load to raw_data.stock_daily_data.")
print("!!!ROWS IN TABLE!!!:", con.execute(f"SELECT COUNT(*) FROM raw_data.stock_daily_data").fetchone()[0]) # type: ignore

#### RAW TRADE DATA ####

# Create trades_data table with only the relevant files
con.execute(f"""
    CREATE TABLE IF NOT EXISTS raw_data.all_options_trades_data (
            option_ticker VARCHAR,
            security VARCHAR,
            option_type VARCHAR,
            strike_price DOUBLE,
            expiration DATE,
            conditions INT,
            correction INT,
            exchange INT,
            price DOUBLE,
            sip_timestamp BIGINT,
            size INT,
            data_date DATE
        )
""")
print(f"Created raw_data.all_options_trades_data db table")

option_trade_files = get_files_to_load('all_options_trades_data',option_trade_dir, num_files_to_load, con)
# Load only the new files
if option_trade_files:
    con.execute(f"""
        INSERT INTO raw_data.all_options_trades_data
        SELECT 
            ticker AS option_ticker,
            REGEXP_EXTRACT(ticker, '^O:([A-Z]+)\d{{0,1}}\d{{6}}[CP]\d{{8}}$', 1) AS security,
            REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}\d{{6}}([CP])\d{{8}}$', 1) AS option_type,
            CASE
                WHEN REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}\d{{6}}[CP](\d{{8}})$', 1) != ''
                THEN REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}\d{{6}}[CP](\d{{8}})$', 1)::DOUBLE / 1000.0 
                ELSE NULL
            END  AS strike_price,
            CASE
                WHEN REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}(\d{{6}})[CP]\d{{8}}$', 1) != ''
                THEN STRPTIME(REGEXP_EXTRACT(ticker, '^O:[A-Z]+\d{{0,1}}(\d{{6}})[CP]\d{{8}}$', 1), '%y%m%d')::DATE
                ELSE NULL
            END AS expiration,
            conditions,
            correction,
            exchange,
            price,
            sip_timestamp,
            size,
            CAST(
                CASE
                    WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1) != '' 
                    THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1)
                    ELSE NULL
                END AS DATE
            ) AS data_date
        FROM read_csv_auto({option_trade_files}, filename=True)
    """)
    print(f"Loaded data from {len(option_trade_files)} new files into raw_data.all_options_trades_data")
else:
    print("No new data to load to raw_data.all_options_trades_data.")
print("!!!ROWS IN TABLE!!!:", con.execute(f"SELECT COUNT(*) FROM raw_data.all_options_trades_data").fetchone()[0]) # type: ignore

### PROJECT ###
#### SECURITIES ####

# Read bank tickers from banks_test.csv
project_tickers = set()
with open(securities_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        project_tickers.add(row['Security'])
# print(*sorted(project_tickers), sep='\n')

con.execute(f"CREATE SCHEMA IF NOT EXISTS {project};")
print(f"CREATE SCHEMA IF NOT EXISTS {project};")

# Create securities table in DuckDB
con.execute(f"CREATE OR REPLACE TABLE {project}.securities (security VARCHAR)")
con.executemany(f"INSERT INTO {project}.securities VALUES (?)", [(ticker,) for ticker in project_tickers])
print(f"Loaded {project}.securities db table")

con.execute(f"""
    CREATE OR REPLACE TABLE {project}.project_filtered_options_trades AS
    SELECT atd.*
        , round(atd.price * atd.size * 100,2) as trade_value
        , std.open as security_open
        , std.high as security_high
        , std.low as security_low
        , std.close as security_close
        , row_number() OVER (PARTITION BY atd.security ORDER BY trade_value DESC) AS trade_rank
        , occ.name as option_condition_name
    FROM raw_data.all_options_trades_data atd
    JOIN raw_data.stock_daily_data std ON std.security = atd.security AND std.data_date = atd.data_date
    JOIN raw_data.option_condition_codes occ ON occ.id = atd.conditions
    JOIN {project}.securities ps ON ps.security = atd.security
    WHERE 1=1
    AND atd.expiration > atd.data_date -- Options Purchased before Expiration
    AND atd.expiration <= atd.data_date + INTERVAL {expiration_days_out}  DAYS -- Options Expiring in N days
    AND atd.conditions >= 209 -- Filters out Late, Canceled trades
    AND atd.conditions < 248 -- Filters out after market trading
    AND trade_value > {min_trade_value} -- minmum contract size of N
    AND (
        -- (atd.option_type = 'C' AND atd.strike_price > security_low) OR (atd.option_type = 'P' AND atd.strike_price < security_high) -- LOOSE: PARTIALLY OTM FOR DAY
        (atd.option_type = 'C' AND atd.strike_price > security_high) OR (atd.option_type = 'P' AND atd.strike_price < security_low) -- STRICT: FULLY OTM FOR DAY
       )
    ORDER BY atd.security, atd.option_ticker, atd.data_date
""")
print(f"Created and Loaded {project}.project_filtered_options_trades db table")
print("!!!ROWS IN TABLE!!!:", con.execute(f"SELECT COUNT(*) FROM {project}.project_filtered_options_trades").fetchone()[0]) # type: ignore

con.execute(f"""
    CREATE OR REPLACE TABLE {project}.security_percentiles AS
    /* Determining Interquartile Range https://en.wikipedia.org/wiki/Interquartile_range */
    SELECT ftd.security
        , min(ftd.expiration - ftd.data_date) AS min_date_from_expiration
        , max(ftd.expiration - ftd.data_date)  max_date_from_expiration
        , count(*) as qualifying_trades
        , ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY size),2) AS q1_size
        , ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY size),2)  AS q3_size
        , q3_size - q1_size AS iqr_size
        , q3_size + (1.5 * iqr_size) AS trad_iqr_size
        , ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY trade_value),2)  AS q1_trade_value
        , ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY trade_value),2)  AS q3_trade_value
        , q3_trade_value - q1_trade_value AS iqr_trade_value
        , q3_trade_value + (1.5 * iqr_trade_value) AS trad_iqr_trade_value
        , {custom_range_filter} as n_range
        , ROUND(PERCENTILE_CONT({custom_range_filter}) WITHIN GROUP (ORDER BY size),2)  AS n_size
        , ROUND(PERCENTILE_CONT({custom_range_filter}) WITHIN GROUP (ORDER BY trade_value),2)  AS n_trade_value
        , ROUND((n_trade_value - q3_trade_value) / iqr_trade_value, 2) AS custom_k
    FROM {project}.project_filtered_options_trades ftd
    WHERE trade_rank <= 1000 -- top N trades matching the previous filtering criteria
    GROUP BY ftd.security
""")
print(f"Created and Loaded {project}.security_percentiles db table")
print("!!!ROWS IN TABLE!!!:", con.execute(f"SELECT COUNT(*) FROM {project}.security_percentiles").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
perc_output = Path(f"{output_dir}/security_percentiles.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {project}.security_percentiles
        ORDER BY security
    ) TO '{perc_output}' (HEADER, DELIMITER ',')
""")
print(f"Security percentiles data written to {perc_output}")

### WHAT TRADES AFFECT PRICE ###

#### FIND TRADES THAT ACHIEVED STRIKE ####

con.execute(f"""
    CREATE OR REPLACE TABLE {project}.notable_options_trades AS
    SELECT ftd.security
        , ftd.option_ticker
        , ftd.data_date as trade_date
        , ftd.option_type
        , ftd.expiration
        , ftd.option_condition_name
        , max(ftd.strike_price) as option_strike_price
        , max(ftd.size) as option_size
        , max(sp.trad_iqr_size) as trad_iqr_size
        , max(sp.n_range) as n_range
        , max(sp.n_size) as security_n_size
        , max(ftd.price) as option_price
        , max(ftd.trade_value) as option_trade_value
        , NTILE({number_of_bins}) OVER (PARTITION BY ftd.security ORDER BY option_trade_value desc) as option_trade_value_bin
        , max(sp.trad_iqr_trade_value) as trad_iqr_trade_value
        , max(sp.n_trade_value) as security_n_trade_value
        , min(CASE WHEN sdd.data_date > ftd.data_date THEN sdd.data_date END) as stock_min_date
        , max(CASE WHEN sdd.data_date > ftd.data_date THEN sdd.data_date END) as stock_max_date
        , max(CASE WHEN sdd.data_date > ftd.data_date THEN sdd.high END) as highest_price_in_period
        , min(CASE WHEN sdd.data_date > ftd.data_date THEN sdd.low END) as lowest_price_in_period
        , max(CASE WHEN sdd.data_date = ftd.expiration THEN sdd.high END) as expiration_high
        , min(CASE WHEN sdd.data_date = ftd.expiration THEN sdd.low END) as expiration_low
        , max(CASE WHEN sdd.data_date = ftd.expiration THEN sdd.close END) as expiration_close
        , CASE
            WHEN ftd.option_type = 'C' THEN
                CASE
                    WHEN option_strike_price <= expiration_close THEN '1C. Option Close ITM'
                    WHEN option_strike_price <= expiration_high THEN '2C. Option Close Temp ITM'
                    WHEN option_strike_price <= highest_price_in_period THEN '3C. Option Temp ITM'
                    ELSE '4C. Option Stay OTM'
                END
            WHEN ftd.option_type = 'P' THEN
                CASE
                    WHEN option_strike_price >= expiration_close THEN '1P. Option Close ITM'
                    WHEN option_strike_price >= expiration_low THEN '2P. Option Close Temp ITM'
                    WHEN option_strike_price >= lowest_price_in_period THEN '3P. Option Temp ITM'
                    ELSE '4P. Option Stay OTM'
                END
          END as itm_otm_category
    FROM {project}.project_filtered_options_trades ftd
    JOIN {project}.security_percentiles sp on sp.security = ftd.security
    JOIN raw_data.stock_daily_data sdd ON sdd.security = ftd.security AND sdd.data_date >= ftd.data_date AND sdd.data_date <= ftd.expiration
    WHERE 1=1
        AND ftd.trade_value >= sp.q3_trade_value
        -- AND ftd.trade_value >= sp.trad_iqr_trade_value
    GROUP BY ftd.security
        , ftd.option_ticker
        , ftd.data_date
        , ftd.option_type
        , ftd.expiration
        , ftd.option_condition_name
""")
print(f"Created and Loaded {project}.notable_options_trades db table")
print("!!!ROWS IN TABLE!!!:", con.execute(f"SELECT COUNT(*) FROM {project}.notable_options_trades").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
notable_options_trades_output = Path(f"{output_dir}/notable_options_trades.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {project}.notable_options_trades ftd
        ORDER BY security, expiration, itm_otm_category, trade_date, option_trade_value desc
    ) TO '{notable_options_trades_output}' (HEADER, DELIMITER ',')
""")
print(f"Notable trade data written to {notable_options_trades_output}")

# Output {project}_percentiles files and baseline file
trade_bins_output = Path(f"{output_dir}/security_options_bins.csv")
con.execute(f"""
    COPY (
    SELECT  security
            , option_trade_value_bin
            , count(CASE WHEN itm_otm_category ilike '%ITM' THEN 1 END) * 1.0 as itm
            , count(CASE WHEN itm_otm_category ilike '%OTM' THEN 1 END) * 1.0 as otm
            , count(*) * 1.0 as cnt
            , count(CASE WHEN itm_otm_category[1] = '1' THEN 1 END) * 1.0 as itm_1
            , count(CASE WHEN itm_otm_category[1] = '2' THEN 1 END) * 1.0 as itm_2
            , count(CASE WHEN itm_otm_category[1] = '3' THEN 1 END) * 1.0 as itm_3
            , round(itm / cnt, 2) as itm_pct
            , min(option_trade_value) as min_trade_value
            , median(option_trade_value) as med_trade_value
            , round(stddev(option_trade_value),2) as stddev_trade_value
    FROM  {project}.notable_options_trades
    GROUP BY 1,2
    ORDER BY 1,2
    ) TO '{trade_bins_output}' (HEADER, DELIMITER ',')
""")
print(f"Notable trade bin data written to {trade_bins_output}")