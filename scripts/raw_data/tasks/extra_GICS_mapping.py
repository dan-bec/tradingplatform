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
import duckdb
import pandas as pd

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

# Function to get GICS classification from MarketWatch
def get_gics_classification(ticker):
    url = f"https://www.marketwatch.com/investing/stock/{ticker.lower()}"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Example: Extract sector and industry from page
        sector_elem = soup.find('span', class_='sector-class')  # Adjust class based on actual HTML
        industry_elem = soup.find('span', class_='industry-class')
        sector = sector_elem.text if sector_elem else 'Financials'  # Default for SPACs
        industry = industry_elem.text if industry_elem else 'Diversified Financial Services'
        return sector, industry
    except:
        # Fallback for SPACs or missing data
        return 'Financials', 'Diversified Financial Services'

# Process tickers and store in database
data = []
for ticker in tickers:
    sector, industry = get_gics_classification(ticker)
    data.append({'ticker': ticker, 'sector': sector, 'industry': industry})

# Convert to DataFrame and store in DuckDB
df = pd.DataFrame(data)
con.execute(f"CREATE OR REPLACE TABLE {raw_schema}.gics_classifications_unclassified (ticker VARCHAR, sector VARCHAR, industry VARCHAR)")
con.execute(f"INSERT INTO {raw_schema}.gics_classifications_unclassified SELECT * FROM df")

print("GICS classifications stored in database.")