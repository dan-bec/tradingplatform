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
stddev_100_file = output_dir / "_stddev_100_file.csv"
baseline_file = output_dir / "_baseline_file.csv"
expiration_days_out = 40

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

# Identify the latest and earliest files
latest_file = valid_files[0]
latest_date = latest_file[0]
print(latest_date)
earliest_file = valid_files[-1]
earliest_date = earliest_file[0]
print(earliest_date)

# Read bank tickers from banks_test.csv
bank_tickers = set()
with open(banks_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        bank_tickers.add(row['Security'])

# Load the last 100 files into DuckDB
last_n_files = valid_files[:100]
file_paths = [str(file[1]) for file in last_n_files]
con.execute(f"""
    CREATE TABLE all_data AS
    SELECT ticker AS option_ticker
        ,volume
        ,open
        ,close
        ,high
        ,low
        ,window_start
        ,transactions
        ,CAST(
            CASE
                WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1) != '' 
                THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1)
                ELSE NULL
            END AS DATE
        ) AS data_date
    FROM read_csv_auto({file_paths}, filename=True)
""")

# Create securities table in DuckDB
con.execute("CREATE TABLE securities (security VARCHAR)")
con.executemany("INSERT INTO securities VALUES (?)", [(ticker,) for ticker in bank_tickers])

# Create parsed_data with filters based on securities and expiration_days_out
con.execute("""
    CREATE TABLE parsed_data AS
    WITH _parsed_all_data AS (
        SELECT 
        ad.*,
        REGEXP_EXTRACT(ad.option_ticker, '^O:([A-Z]+)\d{6}[CP]\d{8}$', 1) AS security,
        REGEXP_EXTRACT(ad.option_ticker, '^O:[A-Z]+\d{6}([CP])\d{8}$', 1) AS option_type,
        CAST(REGEXP_EXTRACT(ad.option_ticker, '^O:[A-Z]+\d{6}[CP](\d{8})$', 1) AS DOUBLE) / 1000.0 AS strike_price
    FROM all_data ad
    WHERE ad.option_ticker IS NOT NULL 
    AND ad.option_ticker != '' 
    AND regexp_matches(ad.option_ticker, '^O:[A-Z]+\d{6}[CP]\d{8}$')
    )

    SELECT 
        pad.data_date,
        pad.security,
        pad.option_ticker,
        STRPTIME(REGEXP_EXTRACT(pad.option_ticker, '^O:[A-Z]+(\d{6})[CP]\d{8}$', 1), '%y%m%d')::DATE AS expiration,
        pad.option_type,
        pad.strike_price,
        CAST(pad.volume AS INTEGER) AS volume,
        CAST(pad.transactions AS INTEGER) AS transactions
    FROM _parsed_all_data pad
    WHERE pad.security IN (SELECT security FROM securities)
      AND expiration > pad.data_date
      AND expiration <= (pad.data_date + INTERVAL 40 DAYS)
      AND CAST(pad.volume AS INTEGER) >= 10
    ORDER BY pad.security ASC, pad.option_ticker ASC, pad.data_date DESC
""")

# Create all_options from parsed_data
con.execute("""
    CREATE TABLE all_options AS
    SELECT DISTINCT option_ticker, security, expiration, option_type, strike_price
    FROM parsed_data
""")

# Create trading_days table with ranked days
con.execute("""
    CREATE TABLE trading_days AS
    SELECT ot.option_ticker,
            dt.data_date,
            ROW_NUMBER() OVER (PARTITION BY ot.option_ticker ORDER BY dt.data_date DESC) AS day_rank
    FROM (SELECT option_ticker,MAX(data_date) as max_data_date FROM parsed_data GROUP BY option_ticker) AS ot
    CROSS JOIN (SELECT DISTINCT data_date FROM parsed_data) AS dt
    WHERE ot.max_data_date >= dt.data_date
""")

# Export pre_aggregated_data
con.execute(f"""
    COPY (
        SELECT * FROM parsed_data
    ) TO '{pre_aggregated_file}' (HEADER, DELIMITER ',')
""")
print(f"Sorted pre-aggregated data written to {pre_aggregated_file}")

# Create aggregated_data
con.execute("""
    CREATE TABLE aggregated_data AS
    WITH _windowed_data AS (
        SELECT 
            p.security,
            p.option_ticker,
            p.expiration,
            p.option_type,
            p.strike_price,
            p.volume,
            p.data_date,
            t.day_rank,
            MAX(p.data_date) OVER (PARTITION BY p.security) AS max_data_date,
            MIN(p.data_date) OVER (PARTITION BY p.security) AS min_data_date
        FROM parsed_data p
        JOIN trading_days t ON p.data_date = t.data_date AND p.option_ticker = t.option_ticker
    )
    SELECT 
        min_data_date,
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
        COALESCE(ROUND(STDDEV(volume) FILTER (WHERE day_rank <= 50), 3), '0.000') AS last_50_std_volume,
        COALESCE(COUNT(option_ticker) FILTER (WHERE day_rank <= 100), 0) AS last_100_count,
        COALESCE(ROUND(AVG(volume) FILTER (WHERE day_rank <= 100), 2), '0.00') AS last_100_avg_volume,
        COALESCE(ROUND(MEDIAN(volume) FILTER (WHERE day_rank <= 100), 2), '0.00') AS last_100_median_volume,
        COALESCE(ROUND(STDDEV(volume) FILTER (WHERE day_rank <= 100), 3), '0.000') AS last_100_std_volume
    FROM _windowed_data
    GROUP BY security, option_ticker, min_data_date, max_data_date, expiration, option_type, strike_price
    ORDER BY security, option_ticker
""")

# Export post_aggregated_data
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
            WHEN COUNT(option_ticker) FILTER (last_100_std_volume > last_100_median_volume) > 0 THEN 100
            ELSE 0
        END AS anomaly_category       
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
            WHEN sc.anomaly_category = 100 AND (ad.last_100_std_volume > ad.last_100_median_volume) THEN ad.last_100_median_volume + (1 * ad.last_100_std_volume) 
            WHEN sc.anomaly_category = 0 THEN GREATEST(ad.last_9_median_volume + (1 * ad.last_9_std_volume), ad.last_21_median_volume + (1 * ad.last_21_std_volume), ad.last_50_median_volume + (1 * ad.last_50_std_volume), ad.last_100_median_volume + (1 * ad.last_100_std_volume))
        END) AS anomaly_volume 
    FROM aggregated_data ad
    JOIN _security_category sc ON ad.security = sc.security
    WHERE ad.last_100_count > 0
    GROUP BY 1,2,3
""")

# Output STDDEV files and baseline file
con.execute(f"""
    COPY (
        SELECT a.*, ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 9 AND a.last_9_count > 0
    ) TO '{stddev_9_file}' (HEADER, DELIMITER ',')
""")
print(f"Sorted pre-aggregated data written to {stddev_9_file}")

con.execute(f"""
    COPY (
        SELECT a.*, ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 21 AND a.last_21_count > 0
    ) TO '{stddev_21_file}' (HEADER, DELIMITER ',')
""")
print(f"Sorted pre-aggregated data written to {stddev_21_file}")

con.execute(f"""
    COPY (
        SELECT a.*, ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 50 AND a.last_50_count > 0
    ) TO '{stddev_50_file}' (HEADER, DELIMITER ',')
""")
print(f"Sorted pre-aggregated data written to {stddev_50_file}")

con.execute(f"""
    COPY (
        SELECT a.*, ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 100 AND a.last_100_count > 0
    ) TO '{stddev_100_file}' (HEADER, DELIMITER ',')
""")
print(f"Sorted pre-aggregated data written to {stddev_100_file}")

con.execute(f"""
    COPY (
        SELECT a.*, ar.anomaly_category, ar.anomaly_volume
        FROM aggregated_data a
        JOIN anomaly_recency ar ON a.security = ar.security
        WHERE ar.anomaly_category = 0
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

# Run anomalous_trades.py script
script_dir = os.path.dirname(os.path.abspath(__file__))
anomalous_trades_path = os.path.join(script_dir, "anomalous_trades.py")
subprocess.run([
    sys.executable, anomalous_trades_path,
    "--db_path", str(full_db_path),
    "--output_dir", str(output_dir)
])