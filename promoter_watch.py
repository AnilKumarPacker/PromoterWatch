import pandas as pd
import requests
from datetime import datetime, timedelta

# Constants for filtering
LOOKBACK_DAYS = 7
SIGNIFICANT_VALUE_CRITERIA = 5000000  # ₹50 Lakhs for 'High Conviction' flag

def fetch_nse_insider_data():
    """Fetches insider trading data from NSE's JSON endpoint."""
    url = "https://www.nseindia.com/api/corporates-pit"
    
    # NSE requires specific headers to avoid being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br"
    }
    
    # Establish a session to handle cookies
    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers) # Get initial cookies
    
    params = {
        "index": "equities",
        "from_date": (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%m-%Y"),
        "to_date": datetime.now().strftime("%d-%m-%Y")
    }
    
    response = session.get(url, headers=headers, params=params)
    return response.json()['data']

def process_data(raw_data):
    df = pd.DataFrame(raw_data)
    
    # 1. Basic Cleaning & Filters
    # Filter for Promoter/Promoter Group only
    df = df[df['personCategory'].str.contains('Promoter', case=False, na=False)]
    
    # Filter for 'Market Purchase' (Exclude Pledges, Inter-se, Allotments)
    # Common mode 'Market Purchase' or 'Buy'
    df = df[df['acqMode'] == 'Market Purchase']
    
    # Convert numeric columns
    df['noOfSecurities'] = pd.to_numeric(df['noOfSecurities'], errors='coerce')
    df['valueInRs'] = pd.to_numeric(df['valueInRs'], errors='coerce')
    
    # 2. Extract specific columns
    report_df = df[['symbol', 'personName', 'noOfSecurities', 'secVal', 'dateOfAcquisitionFrom']].copy()
    report_df.columns = ['Stock Name', 'Promoter Buyer', 'Qty', 'Avg Price', 'Date']
    
    # 3. High Conviction Logic
    # Group by Stock to find multiple promoters buying
    conviction_counts = report_df.groupby('Stock Name')['Promoter Buyer'].transform('nunique')
    
    report_df['Observations'] = ""
    report_df.loc[conviction_counts > 1, 'Observations'] += "🔥 Multiple Promoters Buying; "
    report_df.loc[df['valueInRs'] > SIGNIFICANT_VALUE_CRITERIA, 'Observations'] += "💰 Significant Value; "
    
    return report_df

if __name__ == "__main__":
    data = fetch_nse_insider_data()
    final_report = process_data(data)
    final_report.to_csv("insider_report.csv", index=False)
    print("Report generated successfully.")
