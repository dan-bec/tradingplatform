import config
from pathlib import Path
import time
import duckdb
import pandas as pd
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--itm-threshold", type=float, default=config.ITM_THRESHOLD, help="ITM threshold")
args = parser.parse_args()

### SETTINGS ###
full_db_path = config.FULL_DB_PATH
prep_schema = config.PREP
itm_threshold = args.itm_threshold
output_dir = config.PREP_OUTPUT_DIR
output_dir.mkdir(parents=True, exist_ok=True)

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Connect to DuckDB
con = duckdb.connect(full_db_path)

# Pre-aggregate results based on binning
con.execute(f"""
    CREATE OR REPLACE TABLE {prep_schema}.itm_percentages AS
    WITH _prep_data AS (
        SELECT ftd.security, ftd.sector, ftd.industry
        , CASE
            WHEN ftd.trade_value >= sp.p999999_trade_value  THEN '1. p999999_trade_value'
            WHEN ftd.trade_value >= sp.p99999_trade_value   THEN '2. p99999_trade_value'
            WHEN ftd.trade_value >= sp.p9999_trade_value    THEN '3. p9999_trade_value'
            WHEN ftd.trade_value >= sp.p999_trade_value     THEN '4. p999_trade_value'
            WHEN ftd.trade_value >= sp.p99_trade_value      THEN '5. p99_trade_value'
            WHEN ftd.trade_value >= sp.p95_trade_value      THEN '6. p95_trade_value'
            WHEN ftd.trade_value >= sp.p90_trade_value      THEN '7. p90_trade_value'
            WHEN ftd.trade_value >= sp.p75_trade_value      THEN '8. p75_trade_value'
            ELSE 'IGNORE'
        END as trade_value_category
        , max(ftd.trade_value) as max_trade_value
        , min(ftd.trade_value) as min_trade_value
        , sum(ftd.itm) as itm_total
        , count(*) * 1.0 as total
        , itm_total / total as itm_pct
        FROM {prep_schema}.filtered_short_term_otm_options_trades ftd
        JOIN {prep_schema}.security_percentiles sp on ftd.security = sp.security
        WHERE ftd.trade_value >= sp.p75_trade_value 
        GROUP BY ftd.sector, ftd.industry, ftd.security, trade_value_category
    )

    SELECT *
    , sum(itm_total) OVER (PARTITION BY security ORDER BY trade_value_category) as itm_running_total 
    , sum(total) OVER (PARTITION BY security ORDER BY trade_value_category) * 1.0 as running_total
    , itm_running_total / running_total as itm_running_pct
    FROM _prep_data
    ORDER BY security, trade_value_category
""")
print(f"Created and Loaded {prep_schema}.security_percentiles db table")
print(f"!!!ROWS IN {prep_schema}.security_percentiles!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.security_percentiles").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
perc_output = Path(f"{output_dir}/itm_percentages.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {prep_schema}.itm_percentages
        ORDER BY security
    ) TO '{perc_output}' (HEADER, DELIMITER ',')
""")
print(f"ITM percentiles data written to {perc_output}")

# Load data from itm_percentages
df = con.execute(f"SELECT * FROM {prep_schema}.itm_percentages").fetchdf()

# Extract category number from trade_value_category (e.g., '1. p999999_trade_value' -> 1)
df['cat_num'] = df['trade_value_category'].str.extract('(\d+)').astype(int)

# Sort by security and category number
df = df.sort_values(by=['security', 'cat_num'])

# Function to compute unusual_baseline, trade_value_category, and running_total for each security group
def compute_unusual_baseline(group):
    if group.empty:
        return pd.DataFrame({
            'unusual_baseline': [None],
            'trade_value_category': [None],
            'number_of_trades': [None]
        })
    
    # Filter the group: include categories 1 and 2 only if min_trade_value <= 1,000,000, and always include categories >= 3
    include_mask = ((group['cat_num'] <= 2) & (group['min_trade_value'] <= 1_000_000)) | (group['cat_num'] >= 3)
    filtered_group = group[include_mask].sort_values('cat_num')
    
    if filtered_group.empty:
        return pd.DataFrame({
            'unusual_baseline': [None],
            'trade_value_category': [None],
            'number_of_trades': [None]
        })
    
    for i in range(len(filtered_group)):
        current = filtered_group.iloc[i]
        if current['itm_pct'] < itm_threshold:
            if i == 0:
                return pd.DataFrame({
                    'unusual_baseline': [None],
                    'trade_value_category': [None],
                    'number_of_trades': [None]
                })
            else:
                prev = filtered_group.iloc[i - 1]
                return pd.DataFrame({
                    'unusual_baseline': [prev['min_trade_value']],
                    'trade_value_category': [prev['trade_value_category']],
                    'number_of_trades': [prev['running_total']]
                })
    # If all itm_pct >= itm_threshold, return the last min_trade_value, category, and running_total
    last = filtered_group.iloc[-1]
    return pd.DataFrame({
        'unusual_baseline': [last['min_trade_value']],
        'trade_value_category': [last['trade_value_category']],
        'number_of_trades': [last['running_total']]
    })

# Step 1: Extract unique 'sector' and 'industry' for each 'security'
security_info = df.groupby('security')[['sector', 'industry']].first().reset_index()

# Step 2: Compute 'unusual_baseline', 'trade_value_category', and 'running_total'
unusual_baselines = df.groupby('security').apply(
    lambda g: compute_unusual_baseline(g[['cat_num', 'min_trade_value', 'itm_pct', 'trade_value_category', 'running_total']]),
    include_groups=False
).reset_index()

# Since apply returns a DataFrame with one row per group, reset the index to make 'security' a column
unusual_baselines = unusual_baselines.reset_index(drop=True)

# Step 3: Merge the results
result = security_info.merge(unusual_baselines, on='security')


# Save to a new table in DuckDB
con.execute(f"CREATE OR REPLACE TABLE {prep_schema}.unusual_baselines AS SELECT * FROM result")

# Optionally save to CSV
result.to_csv(f"{output_dir}/unusual_baselines.csv", index=False)

# Close connection
con.close()

# Print execution time
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")