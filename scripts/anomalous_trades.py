import duckdb
from pathlib import Path
import argparse
import time

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Set up argument parser
parser = argparse.ArgumentParser(description="Process option data from DuckDB database.")
parser.add_argument("--db_path", required=True, help="Path to the DuckDB database file.")
parser.add_argument("--output_dir", required=True, help="Path to the output directory.")
args = parser.parse_args()

# Convert string arguments to Path objects
db_path = Path(args.db_path)
output_dir = Path(args.output_dir)

# Connect to the DuckDB database
con = duckdb.connect(str(db_path))

# Step 1: Join parsed_data to anomaly_recency on security and trading_days on data_date
con.execute("""
    CREATE OR REPLACE VIEW expanded_parsed_data AS
    SELECT 
        pd.*,
        ar.anomaly_category,
        ar.anomaly_volume,
        td.day_rank
    FROM parsed_data pd
    JOIN anomaly_recency ar ON pd.security = ar.security
    JOIN trading_days td ON pd.data_date = td.data_date AND pd.option_ticker = td.option_ticker
""")
print(f"Created expanded_parsed_data db table")

# Step 32: Filter for volume >= anomaly_volume
con.execute("""
    CREATE OR REPLACE TABLE full_daily_data AS
    SELECT *
    FROM expanded_parsed_data
    WHERE volume >= anomaly_volume
""")
print(f"Created full_daily_data db table")

# Create subfolders within the provided output_dir
investigate_dir = output_dir / "investigate"
investigate_dir.mkdir(parents=True, exist_ok=True)
baseline_dir = output_dir / "baseline"
baseline_dir.mkdir(parents=True, exist_ok=True)

# Export for anomaly_category > 0 to "investigate" folder
securities_anomaly = con.execute("SELECT DISTINCT security, anomaly_category FROM investigate_daily_data").fetchall()
for security, category in securities_anomaly:
    file_path = investigate_dir / f"{security}_{category}_daily_anomalies.csv"
    con.execute(f"COPY (SELECT * FROM investigate_daily_data WHERE security = ?) TO '{str(file_path)}' (HEADER, DELIMITER ',')", (security,))
print(f"Created securities_anomaly list")

# Export for anomaly_category = 0 to "baseline" folder
securities_baseline = con.execute("SELECT DISTINCT security FROM baseline_daily_data").fetchall()
for security, in securities_baseline:
    file_path = baseline_dir / f"{security}_0_daily_anomalies.csv"
    con.execute(f"COPY (SELECT * FROM baseline_daily_data WHERE security = ?) TO '{str(file_path)}' (HEADER, DELIMITER ',')", (security,))
print(f"Created securities_baseline list")
# Additional Trade Data Processing

# Get unique dates from investigate_daily_data
dates = [row[0] for row in con.execute("SELECT DISTINCT data_date FROM investigate_daily_data order by data_date").fetchall()]
print("Distinct dates from investigate_daily_data, sorted:")
for date in dates:
    print(date)
print(f"Created trade dates list")

# Build file paths for those dates
file_paths = [str(Path("data/options/trades") / f"{date}.csv") for date in dates]

# Create trades_data table with only the relevant files
con.execute(f"""
    CREATE OR REPLACE TABLE trades_data AS
    SELECT *,
        CAST(
            CASE
                WHEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1) != '' 
                THEN REGEXP_EXTRACT(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.csv$', 1)
                ELSE NULL
            END AS DATE
        ) AS data_date
    FROM read_csv_auto({file_paths}, filename=True)
""")
print(f"Created trades_data db table")

# Create filtered_trades table by joining and filtering
con.execute("""
    CREATE OR REPLACE TABLE filtered_trades AS
    SELECT 
        td.data_date,
        td.ticker as option_ticker,
        td.size,
        td.price,
        td.price * td.size * 100 as trade_value,
        CASE 
            WHEN trade_value < 100_000 THEN '<$0.1M'
            WHEN trade_value < 300_000 THEN '$0.1M-$0.3M'
            WHEN trade_value < 1_000_000 THEN '$0.3M-$1.0M'
            WHEN trade_value < 3_000_000 THEN '$1.0M-$3.0M'
            WHEN trade_value < 10_000_000 THEN '$3.0M-$10.0M'
            WHEN trade_value >= 10_000_000 THEN '+$10M'
        END as trade_value_bracket,
        td.sip_timestamp,
        td.conditions,
        td.correction,
        td.exchange,
        occ.id,
        occ.name,
        occ.type,
        occ.data_types,
        fdd.security,
        fdd.expiration,
        fdd.option_type,
        fdd.strike_price,
        fdd.volume,
        fdd.transactions,
        fdd.anomaly_category,
        fdd.anomaly_volume,
        fdd.day_rank
    FROM trades_data td
    JOIN full_daily_data fdd 
        ON td.ticker = fdd.option_ticker AND td.data_date = fdd.data_date
    LEFT JOIN option_condition_codes occ
        ON occ.id = td.conditions
    WHERE td.size > (fdd.volume * 2.0 / fdd.transactions)
    AND fdd.transactions > 0
    AND trade_value > 300_000
    ORDER BY fdd.security,td.ticker,td.data_date
""")
print(f"Created filtered_trades db table")

# Export filtered trades per security to "investigate" folder
for security, category in securities_anomaly:
    file_path = investigate_dir / f"{security}_{category}_trades.csv"
    con.execute(f"COPY (SELECT * FROM filtered_trades WHERE security = ?) TO '{str(file_path)}' (HEADER, DELIMITER ',')", (security,))
    print(f"Large trade data written to '{str(file_path)}/{security}_{category}_trades.csv")

# Output Baseline File
large_trades_path = output_dir / f"_large_trades.csv"
con.execute(f"""
    COPY (
        SELECT * 
        FROM filtered_trades 
        ORDER BY security, expiration, trade_value desc
    ) TO '{large_trades_path}' (HEADER, DELIMITER ',')
""")
print(f"Large trade data written to {large_trades_path}")

# Close the database connection
con.close()

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")