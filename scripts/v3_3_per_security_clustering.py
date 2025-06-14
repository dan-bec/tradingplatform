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
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from kneed import KneeLocator

### SETTINGS ###
data_path = 'data'
full_db_path = Path(f"{data_path}/master_database.db")
prep_schema = 'prep'
output_dir = Path(f"./projects/{prep_schema}/outputs")
output_dir.mkdir(parents=True, exist_ok=True)
custom_range_filter = .9
number_of_bins = 20
use_log_transform = False  # Parameter to toggle log transformation for trade_value
max_k = 10  # Maximum number of clusters to test per bin

# Capture and print start time
start_time = time.time()
print(f"Start time: {start_time:.2f} seconds")

# Connect to DuckDB
con = duckdb.connect(full_db_path)

# Pre-aggregate results based on binning
con.execute(f"""
    CREATE OR REPLACE TABLE {prep_schema}.security_percentiles AS
    /* Determining Interquartile Range https://en.wikipedia.org/wiki/Interquartile_range */
    SELECT ftd.security
        , ftd.sector
        , ftd.industry
        , min(ftd.expiration - ftd.data_date) AS min_dte
        , max(ftd.expiration - ftd.data_date)  max_dte
        , count(*) as qualifying_trades
        , ntile({number_of_bins}) OVER (ORDER BY count(*) desc) as qualifying_trades_bin
        , MIN(trade_value) AS p0_trade_value
        , ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY trade_value),2)  AS p25_trade_value
        , ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY trade_value),2)  AS p75_trade_value
        , p75_trade_value - p25_trade_value AS iqr
        , p75_trade_value + (1.5 * iqr) AS trad_iqr_trade_value
        , {custom_range_filter} as n_range
        , ROUND(PERCENTILE_CONT({custom_range_filter}) WITHIN GROUP (ORDER BY trade_value),2)  AS pn_trade_value
        , ROUND((pn_trade_value - p75_trade_value) / iqr, 2) AS custom_k
        , ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY trade_value),2)  AS p90_trade_value
        , ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY trade_value),2)  AS p95_trade_value
        , ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY trade_value),2)  AS p99_trade_value
        , ROUND(PERCENTILE_CONT(0.999) WITHIN GROUP (ORDER BY trade_value),2)  AS p999_trade_value
        , ROUND(PERCENTILE_CONT(0.9999) WITHIN GROUP (ORDER BY trade_value),2)  AS p9999_trade_value
        , ROUND(PERCENTILE_CONT(0.99999) WITHIN GROUP (ORDER BY trade_value),2)  AS p99999_trade_value
        , ROUND(PERCENTILE_CONT(0.999999) WITHIN GROUP (ORDER BY trade_value),2)  AS p999999_trade_value
    FROM {prep_schema}.filtered_short_term_otm_options_trades ftd
    GROUP BY ftd.security, ftd.sector, ftd.industry
    ORDER BY ftd.security, ftd.sector, ftd.industry
""")
print(f"Created and Loaded {prep_schema}.security_percentiles db table")
print(f"!!!ROWS IN {prep_schema}.security_percentiles!!!:", con.execute(f"SELECT COUNT(*) FROM {prep_schema}.security_percentiles").fetchone()[0]) # type: ignore

# Output {project}_percentiles files and baseline file
perc_output = Path(f"{output_dir}/security_percentiles.csv")
con.execute(f"""
    COPY (
        SELECT *
        FROM {prep_schema}.security_percentiles
        ORDER BY security
    ) TO '{perc_output}' (HEADER, DELIMITER ',')
""")
print(f"Security percentiles data written to {perc_output}")

# Begin Clustering Analysis
query = f"SELECT * FROM {prep_schema}.filtered_short_term_otm_options_trades"
df = con.execute(query).fetchdf()

# Use raw trade_value
trade_value_col = 'trade_value'
percentile_prefix = 'p'
percentile_suffix = '_trade_value'

# Calculate number of trades per security
trade_counts = df.groupby('security').size().reset_index(name='num_trades')
num_trades_col = 'num_trades'

# Calculate percentiles per security using raw trade_value
quantile_levels = [0.90, 0.95, 0.99, 0.999, 0.9999, 0.99999, 0.999999]
percentiles = df.groupby('security')[trade_value_col].quantile(quantile_levels).unstack().reset_index() # type: ignore
percentile_columns = [f"{percentile_prefix}{int(q * 1000000)}{percentile_suffix}" for q in quantile_levels]
percentiles.columns = ['security'] + percentile_columns

# Merge the features
security_features = trade_counts.merge(percentiles, on='security', how='inner')

# Handle missing values
security_features.fillna(0, inplace=True)

# Step 1: Bin stocks by N.5 part of round(log10(num_trades))
# Calculate log10 of num_trades
log_num_trades = np.log10(security_features['num_trades'].astype(float))

# Round to nearest 0.5
rounded_log = np.round(log_num_trades * 2) / 2

# Multiply by 10 to get bin labels (5, 10, 15, 20, 25, etc.)
security_features['trade_volume_bin'] = (rounded_log * 10).astype(int)

# Step 2: Apply KMeans clustering within each log-based bin with dynamic k using KneeLocator
scaler = StandardScaler()
inertias_dict = {}
silhouette_scores_dict = {}
optimal_k_dict = {}

for bin_label in security_features['trade_volume_bin'].unique():
    bin_mask = security_features['trade_volume_bin'] == bin_label
    bin_df = security_features[bin_mask]
    n_samples = len(bin_df)
    if n_samples > 1:
        scaled_percentiles = scaler.fit_transform(bin_df[percentile_columns])
        inertias = []
        k_range = range(1, min(max_k + 1, n_samples))  # Limit k to number of samples
        for k in k_range:
            kmeans = KMeans(n_clusters=k, random_state=42)
            kmeans.fit(scaled_percentiles)
            inertias.append(kmeans.inertia_)
        
        # Determine optimal k using KneeLocator
        if len(k_range) > 2:  # Need at least 3 points for elbow detection
            knee = KneeLocator(list(k_range), inertias, curve='convex', direction='decreasing')
            optimal_k = knee.elbow if knee.elbow else 2  # Default to 2 if no elbow found
        else:
            optimal_k = 1  # Too few samples for multiple clusters
        
        # Perform clustering with optimal k
        kmeans = KMeans(n_clusters=optimal_k, random_state=42)
        cluster_labels = kmeans.fit_predict(scaled_percentiles)
        security_features.loc[bin_mask, 'cluster'] = cluster_labels
        optimal_k_dict[bin_label] = optimal_k
        inertias_dict[bin_label] = inertias
        # Compute silhouette score for optimal k if k > 1
        if optimal_k > 1:
            silhouette_scores_dict[bin_label] = silhouette_score(scaled_percentiles, cluster_labels)
        else:
            silhouette_scores_dict[bin_label] = None
    else:
        security_features.loc[bin_mask, 'cluster'] = 0
        optimal_k_dict[bin_label] = 1
        inertias_dict[bin_label] = []
        silhouette_scores_dict[bin_label] = None

# Plot elbow curves for each bin
plt.figure(figsize=(10, 6))
for bin_label, inertias in inertias_dict.items():
    if inertias:  # Only plot if there are inertia values
        k_range = range(1, len(inertias) + 1)
        plt.plot(k_range, inertias, marker='o', label=f'Bin {bin_label} (k={optimal_k_dict[bin_label]})')
plt.title('Elbow Method for Optimal K by Bin')
plt.xlabel('Number of Clusters')
plt.ylabel('Inertia')
plt.legend()
plt.savefig(output_dir / 'elbow_curve_bins.png')
plt.close()

# Plot silhouette scores for each bin
plt.figure(figsize=(12, 6))
bin_labels = [bl for bl in silhouette_scores_dict if silhouette_scores_dict[bl] is not None]
sil_scores = [silhouette_scores_dict[bl] for bl in bin_labels]
if bin_labels:  # Only plot if there are valid silhouette scores
    plt.bar(bin_labels, sil_scores)
    plt.title('Silhouette Scores for Optimal K by Bin')
    plt.xlabel('Bin Label')
    plt.ylabel('Silhouette Score')
plt.savefig(output_dir / 'silhouette_scores_binned.png')
plt.close()

# After clustering, rank the unique trade_volume_bin values in descending order
unique_bins = security_features['trade_volume_bin'].unique()
sorted_bins = sorted(unique_bins, reverse=True)
bin_to_rank = {bin_val: rank for rank, bin_val in enumerate(sorted_bins, start=1)}

# Create final_cluster using the ranked trade_volume_bin_rank
security_features['final_cluster'] = security_features['trade_volume_bin'].astype(str) + '__' + security_features['cluster'].astype(int).astype(str)

# Update trade_volume_bin to hold the ranks
security_features['trade_volume_bin_rank'] = security_features['trade_volume_bin'].map(bin_to_rank)

# Plot and save cluster visualization without log scales
plt.figure(figsize=(10, 6))
sns.scatterplot(data=security_features, x='trade_volume_bin', y=f'p950000{percentile_suffix}', hue='final_cluster', palette='deep')
plt.title('Security Clusters Based on Trade Features (Binned by log10(num_trades))')
plt.xlabel('Number of Trades')
plt.ylabel('95th Percentile Trade Value')
plt.savefig(output_dir / 'cluster_scatter_binned.png')
plt.close()

# Add sector and industry to security_features
security_info = df.groupby('security').agg({'sector': 'first', 'industry': 'first'}).reset_index()
security_features = security_features.merge(security_info, on='security', how='left')

# Save the clustered securities to DuckDB
con.execute(f"CREATE OR REPLACE TABLE {prep_schema}.clustered_securities AS SELECT * FROM security_features")
print(f"Securities have been clustered: {prep_schema}.clustered_securities")

# Output to CSV
cluster_output = output_dir / "clustered_securities_binned.csv"
con.execute(f"""
    COPY (
        SELECT *
        FROM {prep_schema}.clustered_securities
        ORDER BY security
    ) TO '{cluster_output}' (HEADER, DELIMITER ',')
""")
print(f"Clustered securities data with log binning written to {cluster_output}")

# Explicitly close the connection
con.close()

# Capture and print end time, then calculate duration
end_time = time.time()
print(f"End time: {end_time:.2f} seconds")
duration = end_time - start_time
print(f"Execution time: {duration:.2f} seconds")