import pandas as pd
import requests
from bs4 import BeautifulSoup

def fetch_trendlyne_insider_data():
    url = "https://trendlyne.com/equity/group-insider-trading-sast/"
    
    # In 2026, using a realistic User-Agent is mandatory
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ Failed to fetch data: {response.status_code}")
            return pd.DataFrame()

        # Parse the HTML table directly into Pandas
        tables = pd.read_html(response.text)
        # Usually, the first table contains the latest insider trades
        df = tables[0]
        
        return df

    except Exception as e:
        print(f"❌ Error: {e}")
        return pd.DataFrame()

def filter_promoter_buys(df):
    if df.empty:
        return df
    
    # Trendlyne columns are slightly different:
    # Look for 'Acquisition' in the 'Action' column 
    # and 'Promoter' in the 'Client Category' column
    
    # Standardizing column names for filtering
    df.columns = [c.strip() for c in df.columns]
    
    # Adjust filters based on Trendlyne's 2026 layout
    is_promoter = df['Client Category'].str.contains('Promoter', case=False, na=False)
    is_buy = df['Action'].str.contains('Acquisition', case=False, na=False)
    
    return df[is_promoter & is_buy]

if __name__ == "__main__":
    raw_data = fetch_trendlyne_insider_data()
    report = filter_promoter_buys(raw_data)
    
    if not report.empty:
        report.to_csv("insider_report.csv", index=False)
        print(f"✅ Found {len(report)} promoter buy transactions.")
    else:
        print("📭 No promoter buying detected in the latest disclosures.")
