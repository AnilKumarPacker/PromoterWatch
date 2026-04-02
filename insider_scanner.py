import pandas as pd
import requests
from datetime import datetime, timedelta

# Constants for filtering
LOOKBACK_DAYS = 7
SIGNIFICANT_VALUE_CRITERIA = 5000000  # ₹50 Lakhs for 'High Conviction' flag

def fetch_nse_insider_data():
    """Fetches insider trading data with robust session handling to bypass blocks."""
    url = "https://www.nseindia.com/api/corporates-pit"
    
    # 1. Use a very specific, modern User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    # 2. CRITICAL: Hit the home page first to get a valid 'nsit' cookie
    # Without this, the API will return 403 or 401.
    try:
        session.get("https://www.nseindia.com", timeout=15)
        time.sleep(2) # Brief pause to mimic human behavior
        
        params = {
            "index": "equities",
            "from_date": (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%m-%Y"),
            "to_date": datetime.now().strftime("%d-%m-%Y")
        }
        
        # 3. Request the actual data
        response = session.get(url, params=params, timeout=15)
        
        # 4. Error Handling: Check status before parsing JSON
        if response.status_code != 200:
            print(f"❌ Error: Received status code {response.status_code}")
            print(f"Full response text (first 500 chars): {response.text[:500]}")
            return []

        return response.json().get('data', [])

    except requests.exceptions.JSONDecodeError:
        print("❌ Failed to decode JSON. NSE likely blocked this request.")
        print(f"Response Content: {response.text[:500]}") # Help you see the HTML error
        return []
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        return []

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
