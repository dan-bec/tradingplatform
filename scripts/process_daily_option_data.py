import os
import csv
import re
from datetime import datetime, date, timedelta
from pathlib import Path
import requests
import time
import duckdb
import sys
import os
import subprocess

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Define file paths
data_dir = Path("data/options/daily")
banks_file = Path("data/banks/banks.csv")
output_dir = Path("data/banks/outputs")
full_db_path = output_dir / "banks_database.db"
pre_aggregated_file = output_dir / "pre_aggregated_data.csv"
post_aggregated_file = output_dir / "post_aggregated_data.csv"
stddev_9_file = output_dir / "_stddev_9_file.csv"
stddev_21_file = output_dir / "_stddev_21_file.csv"
stddev_50_file = output_dir / "_stddev_50_file.csv"
baseline_file = output_dir / "_baseline_file.csv"

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

# Function to parse option ticker
def parse_option_ticker(option_ticker):
    """Parses an option ticker into security, expiration date, option type, and strike price."""
    match = re.match(r"O:([A-Z]+)(\d{6})([CP])(\d{8})", option_ticker)
    if match:
        security, exp_str, option_type, strike_str = match.groups()
        year = 2000 + int(exp_str[:2])
        month = int(exp_str[2:4])
        day = int(exp_str[4:6])
        expiration_date = date(year, month, day).strftime("%Y-%m-%d")
        strike_price = int(strike_str) / 1000.0
        return security, expiration_date, option_type, strike_price
    else:
        raise ValueError(f"Invalid option ticker: {option_ticker}")

# Set up API key
script_dir = os.path.dirname(os.path.abspath(__file__))
dataservices_path = os.path.join(script_dir, "..", "src", "BullseyeApp", "Shared", "Data", "DataService.cs")
API_KEY = get_static_string(dataservices_path, "API_KEY")

# Create output directory if it doesn’t exist
os.makedirs(output_dir, exist_ok=True)

# Delete the database file if it exists
if full_db_path.exists():
    full_db_path.unlink()

# Connect to DuckDB
con = duckdb.connect(str(full_db_path))

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
        CREATE OR REPLACE TABLE option_condition_codes (
            id INTEGER,
            type VARCHAR,
            name VARCHAR,
            asset_class VARCHAR,
            data_types VARCHAR
        )
    """)
    for code in condition_codes:
        data_types_str = ",".join(code.get("data_types", []))
        con.execute(
            "INSERT INTO option_condition_codes (id, type, name, asset_class, data_types) VALUES (?, ?, ?, ?, ?)",
            (code.get("id"), code.get("type"), code.get("name"), code.get("asset_class"), data_types_str)
        )
    print("Condition codes fetched and stored in the database.")
else:
    print("No condition codes fetched.")

# Find all valid data files and sort by date descending
all_files = list(data_dir.glob("*.csv"))
valid_files = []
for file in all_files:
    try:
        file_date = datetime.strptime(file.stem, "%Y-%m-%d").date()
        valid_files.append((file_date, file))
    except ValueError:
        continue

if not valid_files:
    print("No valid data files found.")
    exit()

# Sort files by date descending
valid_files.sort(key=lambda x: x[0], reverse=True)

# Identify the latest file
latest_file = valid_files[0]
latest_date = latest_file[0]

# Calculate the expiration date cutoff (latest_date + 62 days)
expiration_cutoff = latest_date + timedelta(days=62)

# Read bank tickers from banks_test.csv
bank_tickers = set()
with open(banks_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        bank_tickers.add(row['Security'])

# Function to get option tickers from Polygon.io API
def get_option_tickers_for_security(api_key, ticker, expiration_date_gte, expiration_date_lte):
    """Fetches option tickers for a given underlying ticker from Polygon.io, only including standard format tickers."""
    base_url = "https://api.polygon.io/v3/reference/options/contracts"
    params = {
        "underlying_ticker": ticker,
        "expiration_date.gte": expiration_date_gte,
        "expiration_date.lte": expiration_date_lte,
        "limit": 1000,
        "apiKey": api_key
    }
    option_tickers = set()
    url = base_url
    first_request = True
    while url:
        if first_request:
            response = requests.get(url, params=params)
            first_request = False
        else:
            response = requests.get(url)
        if response.status_code != 200:
            print(f"API request failed for {ticker}: {response.status_code} - {response.text}")
            break
        data = response.json()
        for contract in data.get("results", []):
            # Only include tickers matching the standard pattern: O:[SYMBOL][6-digit date][C or P][strike]
            if re.match(r"O:[A-Z]+\d{6}[CP]\d+", contract["ticker"]):
                option_tickers.add(contract["ticker"])
        url = data.get("next_url")
        if url:
            time.sleep(1)  # Respect API rate limits
    return option_tickers

# Get distinct options from Polygon.io API for each ticker
latest_date_str = latest_date.strftime("%Y-%m-%d")
expiration_cutoff_str = expiration_cutoff.strftime("%Y-%m-%d")
distinct_options = set()
for ticker in bank_tickers:
    option_tickers = get_option_tickers_for_security(API_KEY, ticker, latest_date_str, expiration_cutoff_str)
    distinct_options.update(option_tickers)
    time.sleep(1)  # Avoid hitting rate limits

# Create option_info dictionary
option_info = {}
for option_ticker in distinct_options:
    try:
        security, expiration, option_type, strike_price = parse_option_ticker(option_ticker)
        option_info[option_ticker] = (security, expiration, option_type, strike_price)
    except ValueError:
        print(f"Skipping invalid option ticker: {option_ticker}")

# Load the last 50 files into DuckDB
last_50_files = valid_files[:50]
file_paths = [str(file[1]) for file in last_50_files]
con.execute(f"""
    CREATE TABLE all_data AS
    SELECT ticker as option_ticker
        ,volume
        ,open
        ,close
        ,high
        ,low
        ,window_start
        ,transactions, 
        CAST(
            CASE
                WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1) != '' 
                THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1)
                ELSE NULL
            END AS DATE
        ) AS data_date
    FROM read_csv_auto({file_paths}, filename=True)
""")

# Create distinct_options table
con.execute("CREATE TABLE distinct_options (option_ticker VARCHAR)")
con.executemany("INSERT INTO distinct_options VALUES (?)", [(ticker,) for ticker in distinct_options])

# Create all_options table with parsed information
con.execute("CREATE TABLE all_options (option_ticker VARCHAR, security VARCHAR, expiration DATE, option_type VARCHAR, strike_price DOUBLE)")
for ticker in distinct_options:
    security, expiration, option_type, strike_price = option_info[ticker]
    con.execute("INSERT INTO all_options VALUES (?, ?, ?, ?, ?)", (ticker, security, expiration, option_type, strike_price))

# Create parsed_data table with filtered and parsed records
con.execute("""
    CREATE TABLE parsed_data AS
    SELECT 
        ad.data_date,
        REGEXP_EXTRACT(ao.option_ticker, 'O:([A-Z]+)(\d{6})([CP])(\d+)', 1) AS security,
        ao.option_ticker,
        ao.expiration,
        ao.option_type,
        ao.strike_price,
        CAST(ad.volume AS INTEGER) AS volume,
        CAST(ad.transactions AS INTEGER) AS transactions
    FROM all_data ad
    JOIN all_options ao on ao.option_ticker = ad.option_ticker
    WHERE CAST(ad.volume AS INTEGER) >= 10
    ORDER BY security ASC, ao.option_ticker ASC, ad.data_date DESC
""")

# Create trading_days table with ranked days
con.execute("""
    CREATE TABLE trading_days AS
    SELECT data_date,
           ROW_NUMBER() OVER (ORDER BY data_date DESC) AS day_rank
    FROM (SELECT DISTINCT data_date FROM parsed_data) AS sub
""")

# Export pre_aggregated_data
con.execute(f"""
    COPY (
        SELECT * FROM parsed_data
    ) TO '{pre_aggregated_file}' (HEADER, DELIMITER ',')
""")

print(f"Sorted pre-aggregated data written to {pre_aggregated_file}")

# Create trading_days table with ranked days
con.execute("""
    CREATE TABLE aggregated_data AS
        WITH _windowed_data AS (
            SELECT 
                a.security,
                a.option_ticker,
                a.expiration,
                a.option_type,
                a.strike_price,
                p.volume,
                p.data_date,
                t.day_rank,
                MAX(p.data_date) OVER (PARTITION BY a.security) AS max_data_date
            FROM all_options a
            LEFT JOIN parsed_data p ON a.option_ticker = p.option_ticker
            LEFT JOIN trading_days t ON p.data_date = t.data_date
        )
        SELECT 
            max_data_date,
            security,
            option_ticker,
            expiration,
            option_type,
            strike_price,
            COALESCE(COUNT(option_ticker) FILTER (WHERE day_rank <= 9), 0) AS last_9_count,
            COALESCE(ROUND(AVG(volume) FILTER (WHERE day_rank <= 9), 2), '0.00') AS last_9_avg_volume,
            COALESCE(ROUND(MEDIAN(volume) FILTER (WHERE day_rank <= 9), 2), '0.00') AS last_9_median_volume,
            COALESCE(ROUND(STDDEV(volume) FILTER (WHERE day_rank <= 9), 3), '0.000') AS last_9_std_volume,
            COALESCE(COUNT(option_ticker) FILTER (WHERE day_rank <= 21), 0) AS last_21_count,
            COALESCE(ROUND(AVG(volume) FILTER (WHERE day_rank <= 21), 2), '0.00') AS last_21_avg_volume,
            COALESCE(ROUND(MEDIAN(volume) FILTER (WHERE day_rank <= 21), 2), '0.00') AS last_21_median_volume,
            COALESCE(ROUND(STDDEV(volume) FILTER (WHERE day_rank <= 21), 3), '0.000') AS last_21_std_volume,
            COALESCE(COUNT(option_ticker) FILTER (WHERE day_rank <= 50), 0) AS last_50_count,
            COALESCE(ROUND(AVG(volume) FILTER (WHERE day_rank <= 50), 2), '0.00') AS last_50_avg_volume,
            COALESCE(ROUND(MEDIAN(volume) FILTER (WHERE day_rank <= 50), 2), '0.00') AS last_50_median_volume,
            COALESCE(ROUND(STDDEV(volume) FILTER (WHERE day_rank <= 50), 3), '0.000') AS last_50_std_volume
        FROM _windowed_data
        GROUP BY security, option_ticker, max_data_date, expiration, option_type, strike_price
        ORDER BY security, option_ticker
""")


# Export post_aggregated_data with aggregations
con.execute(f"""
    COPY (
        SELECT * FROM aggregated_data
    ) TO '{post_aggregated_file}' (HEADER, DELIMITER ',')
""")

print(f"Pivoted post-aggregated data written to {post_aggregated_file}")


# Categorize securities by anomaly recency
con.execute("""
    CREATE TABLE anomaly_recency AS
        WITH _security_category AS (
            SELECT security
            ,CASE
                WHEN COUNT(option_ticker) FILTER (last_9_std_volume > last_9_median_volume) > 0 THEN 9
                WHEN COUNT(option_ticker) FILTER (last_21_std_volume > last_21_median_volume) > 0 THEN 21
                WHEN COUNT(option_ticker) FILTER (last_50_std_volume > last_50_median_volume) > 0 THEN 50
                ELSE 0
            END as anomaly_category       
            FROM aggregated_data
            GROUP BY security
        )
        
        SELECT ad.security
        ,ad.max_data_date
        ,sc.anomaly_category
        ,MEDIAN(CASE
            WHEN sc.anomaly_category = 9 AND (ad.last_9_std_volume > ad.last_9_median_volume) THEN ad.last_9_median_volume + (1 * ad.last_9_std_volume)
            WHEN sc.anomaly_category = 21 AND (ad.last_21_std_volume > ad.last_21_median_volume) THEN ad.last_21_median_volume + (1 * ad.last_21_std_volume)
            WHEN sc.anomaly_category = 50 AND (ad.last_50_std_volume > ad.last_50_median_volume) THEN ad.last_50_median_volume + (1 * ad.last_50_std_volume) 
            WHEN sc.anomaly_category = 0 THEN GREATEST(ad.last_9_median_volume + (1 * ad.last_9_std_volume),ad.last_21_median_volume + (1 * ad.last_21_std_volume),ad.last_50_median_volume + (1 * ad.last_50_std_volume))
        END) as anomaly_volume 
        FROM aggregated_data ad
        JOIN _security_category sc ON ad.security = sc.security
        WHERE ad.last_50_count > 0
        GROUP BY 1,2,3
""")

# Output 9 STDDEV File
con.execute(f"""
    COPY (
        SELECT a.* , ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 9 and a.last_9_count > 0
    ) TO '{stddev_9_file}' (HEADER, DELIMITER ',')
""")

print(f"Sorted pre-aggregated data written to {stddev_9_file}")

# Output 21 STDDEV File
con.execute(f"""
    COPY (
        SELECT a.* , ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 21 and a.last_21_count > 0
    ) TO '{stddev_21_file}' (HEADER, DELIMITER ',')
""")

print(f"Sorted pre-aggregated data written to {stddev_21_file}")

# Output 50 STDDEV File
con.execute(f"""
    COPY (
        SELECT a.* , ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 50 and a.last_50_count > 0
    ) TO '{stddev_50_file}' (HEADER, DELIMITER ',')
""")

print(f"Sorted pre-aggregated data written to {stddev_50_file}")

# Output Baseline File
con.execute(f"""
    COPY (
        SELECT a.* , ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE anomaly_category = 0
    ) TO '{baseline_file}' (HEADER, DELIMITER ',')
""")

print(f"Sorted pre-aggregated data written to {baseline_file}")

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")

# Explicitly close the connection
con.close()

#### RUN ANOMALOUS_TRADES.PY SCRIPT

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the full path to anomalous_trades.py
anomalous_trades_path = os.path.join(script_dir, "anomalous_trades.py")

# Call the downstream script using sys.executable and the full script path
subprocess.run([
    sys.executable, anomalous_trades_path,
    "--db_path", str(full_db_path),
    "--output_dir", str(output_dir)
])


