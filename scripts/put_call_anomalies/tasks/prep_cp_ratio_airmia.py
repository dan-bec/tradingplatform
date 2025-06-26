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

import scripts.put_call_anomalies.config as config
import time
import duckdb
import pandas as pd
import numpy as np
from statsmodels.tsa.stattools import acf
import os
from pmdarima import auto_arima

# Connect to the database (update the path to your database)
con = duckdb.connect('path/to/database.db')

# Define schema and table parameters (replace with actual values)
prep_schema = config.PREP_SCHEMA
atr_max = config.ATR_MAX
table_name = f"{prep_schema}.filtered_options_trades_max_atr_{atr_max}"

# Retrieve data and calculate cp_ratio
query = f"""
SELECT 
    security,
    dte_category,
    data_date,
    SUM(CASE WHEN option_type = 'C' THEN trade_value ELSE 0 END) / SUM(trade_value) as cp_ratio
FROM {table_name}
GROUP BY security, dte_category, data_date
ORDER BY security, dte_category, data_date
"""
df = con.execute(query).fetchdf()

# Function to predict next day's cp_ratio using ARIMA
def predict_next_day_arima(series, min_observations=10):
    """
    Predict the next day's cp_ratio using ARIMA.
    
    Args:
        series (pd.Series): Time series of cp_ratio values
        min_observations (int): Minimum number of observations required for prediction
    
    Returns:
        float or None: Predicted cp_ratio for the next day, or None if prediction fails
    """
    if len(series) < min_observations:
        print(f"Insufficient data: {len(series)} observations, minimum required: {min_observations}")
        return None
    
    try:
        # Use auto_arima to automatically select the best ARIMA parameters
        model = auto_arima(series, seasonal=False, suppress_warnings=True)
        # Fit the model
        model_fit = model.fit(series)
        # Forecast the next day
        forecast = model_fit.predict(n_periods=1)
        return forecast[0]
    except Exception as e:
        print(f"Error in ARIMA prediction: {e}")
        return None

# Process data and generate predictions
predictions = []
grouped = df.groupby(['security', 'dte_category'])

for (security, dte_category), group in grouped:
    # Sort by date to ensure time series order
    group = group.sort_values('data_date')
    # Extract cp_ratio as a time series
    series = group['cp_ratio']
    
    # Predict the next day's cp_ratio
    next_day_prediction = predict_next_day_arima(series)
    if next_day_prediction is not None:
        predictions.append({
            'security': security,
            'dte_category': dte_category,
            'predicted_cp_ratio': next_day_prediction,
            'prediction_date': group['data_date'].max() + pd.Timedelta(days=1)
        })

# Convert predictions to DataFrame
predictions_df = pd.DataFrame(predictions)


# Create the table from the DataFrame
con.execute(f"""
    CREATE OR REPLACE TABLE {prep_schema}.cp_ratio_arima_results AS
    SELECT *
    FROM predictions_df
    order by security, predicted_cp_ratio
""")


# Close the database connection
con.close()

# Save predictions to a CSV file
predictions_df.to_csv('predicted_cp_ratios.csv', index=False)

print("Predictions saved to 'predicted_cp_ratios.csv'")

