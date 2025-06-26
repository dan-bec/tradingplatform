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

import scripts.raw_data.config as config
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import duckdb
import pandas as pd
import time

full_db_path = config.FULL_DB_PATH
stock_summary_dir = config.STOCK_SUMMARY_DIR
sectors_industries_csv = config.SECTORS_CSV
option_trade_dir = config.OPTION_TRADE_DIR
raw_schema = config.RAW_SCHEMA

# Connect to DuckDB
con = duckdb.connect(str(full_db_path))
print(f"Connected to DuckDB database: {full_db_path}")

# List of tickers
tickers = ['AACT',
'AAM',
'AAQC',
'AASP',
'AEAE',
'AFJK',
'AITR',
'ALCY',
'ALF',
'ALSAF',
'AMOD',
'ANSC',
'AOGO',
'APNC',
'APXIF',
'AQUC',
'ARCK',
'ASCBF',
'ATEK',
'ATMC',
'ATMV',
'AVAN',
'AVCTQ',
'AXAC',
'AXHI',
'BACQ',
'BAYA',
'BKHA',
'BMAC',
'BOWN',
'BYNO',
'BZAI',
'CAPN',
'CAPT',
'CBRRF',
'CCIX',
'CCTSF',
'CDAQF',
'CEP',
'CEPO',
'CEPT',
'CHAC',
'CHEB',
'CLBR',
'CLRCF',
'CMCAF',
'CNDA',
'CNXX',
'COOL',
'CRTAF',
'CSLMF',
'CSTAF',
'CUB',
'CURR',
'DAAQ',
'DEVS',
'DIST',
'DMAA',
'DMYY',
'DSAQ',
'DTSQ',
'DYCQ',
'EGOXF',
'EMCG',
'EQV',
'ESHA',
'EURK',
'EVCO',
'EVGRF',
'FERA',
'FGMC',
'FLLC',
'FNVTF',
'FORL',
'FRLA',
'FSAC',
'FSHP',
'FSNB',
'FTII',
'GAPA',
'GATE',
'GDST',
'GGAAF',
'GIG',
'GLACF',
'GLLI',
'GNRSQ',
'GRAF',
'GSHR',
'GTBT',
'HAIAF',
'HLXB',
'HOND',
'HSPO',
'HYAC',
'IBAC',
'IGTA',
'INTE',
'IROH',
'IRRX',
'ISRL',
'IVCAF',
'IVCBF',
'IXAQF',
'JACS',
'JVSA',
'KBSX',
'KVAC',
'LEGT',
'LOKV',
'LPAA',
'MACI',
'MAYA',
'MBAV',
'MCAG',
'MLAC',
'MSSAF',
'NBST',
'NETD',
'NFNT',
'NFSCF',
'NHIC',
'NVAC',
'OAKU',
'OSRH',
'PCSC',
'PHYTF',
'PLMJF',
'PLMK',
'PMGM',
'PMVC',
'POLE',
'PORT',
'PPYA',
'PRBM',
'PRLH',
'PUCK',
'QETA',
'QSEA',
'RAAQ',
'RAC',
'RDAC',
'RENEF',
'RFAI',
'ROSE',
'ROSS',
'SBXD',
'SCRM',
'SDHI',
'SELX',
'SIMA',
'SJ',
'SOUL',
'SPKL',
'SVCC',
'SVII',
'SWSS',
'SZZL',
'TACH',
'TACO',
'TBMC',
'TETEF',
'TGAAF',
'TLGYF',
'TVA',
'USCTF',
'UYSC',
'VACH',
'VCIC',
'VMCAF',
'WARR',
'WELNF',
'WINV',
'WTMA',
'YOTA',
'ZLSSF']  # Subset for demonstration

# GICS mapping rules (simplified)
gics_mapping = {
    'blank check|merger|acquisition': {'sector': 'Finance', 'industry': 'SPAC'},
    'artificial intelligence|software|technology': {'sector': 'Information Technology', 'industry': 'Software'},
    'semiconductor|hardware': {'sector': 'Information Technology', 'industry': 'Semiconductors & Semiconductor Equipment'},
    'healthcare|clinical trial': {'sector': 'Medical', 'industry': 'Medical - Biomedical and Genetics'},
    'cannabis|hemp': {'sector': 'Medical', 'industry': 'Medical - Products'},
    'electric vehicles':{'sector': 'Auto-Tires-Trucks', 'industry': 'Automotive - EV'},
    'streaming|media|social': {'sector': 'Communication Services', 'industry': 'Interactive Media & Services'}
}

def get_business_description(ticker):
    """
    Fetches the business description for a given stock ticker using yfinance.

    Args:
        ticker (str): The stock ticker symbol (e.g., 'AAPL', 'AEAE').

    Returns:
        str: The business description if available, otherwise an empty string.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        description = info.get('longBusinessSummary', '')
        if description:
            return description
        else:
            print(f"No description found for {ticker}")
            return ''
    except Exception as e:
        print(f"Error fetching description for {ticker}: {e}")
        return ''
    finally:
        time.sleep(1)  # Add delay to avoid rate limiting

def assign_gics(ticker, description):
    for keyword, classification in gics_mapping.items():
        if any(k in description.lower() for k in keyword.split('|')):
            return classification['sector'], classification['industry']
    return 'Unknown', 'Unknown'

# Process tickers
data = []
for ticker in tickers:
    description = get_business_description(ticker)
    sector, industry = assign_gics(ticker, description)
    data.append({'ticker': ticker, 'sector': sector, 'industry': industry})

# Convert to DataFrame and store in DuckDB
df = pd.DataFrame(data)
con.execute(f"CREATE OR REPLACE TABLE {raw_schema}.gics_classifications_unclassified (ticker VARCHAR, sector VARCHAR, industry VARCHAR)")
con.execute(f"INSERT INTO {raw_schema}.gics_classifications_unclassified SELECT * FROM df")

print("GICS classifications stored in database.")