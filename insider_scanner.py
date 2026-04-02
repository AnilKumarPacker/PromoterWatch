import pandas as pd
import requests
from bs4 import BeautifulSoup
import os

def fetch_trendlyne_data():
    url = "https://trendlyne.com/equity/group-insider-trading-sast/"
    
    # Modern headers for 2026 to avoid bot detection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        # Trendlyne usually serves standard HTML tables
        # Using 'lxml' as the engine for speed and reliability
        tables = pd.read_html(response.text, flavor='bs4')
        
        if not tables:
            print("❌ No tables found on the page.")
            return pd.DataFrame()

        # The first table is usually the Insider Trading list
        df = tables[0]
        return df

    except Exception as e:
        print(f"❌ Error fetching Trendlyne: {e}")
        return pd.DataFrame()

def process_and_save(df):
    if df.empty:
        print("📭 DataFrame is empty. Skipping save.")
        return

    # Clean column names (Trendlyne often has leading/trailing spaces)
    df.columns = [str(c).strip() for c in df.columns]

    # Filter for Promoters and Buy/Acquisition
    # In 2026, Trendlyne uses 'Client Category' and 'Action'
    try:
        mask = (
            df['Client Category'].str.contains('Promoter', case=False, na=False) &
            df['Action'].str.contains('Acquisition', case=False, na=False)
        )
        filtered_df = df[mask].copy()

        if not filtered_df.empty:
            filtered_df.to_csv("insider_report.csv", index=False)
            print(f"✅ Found {len(filtered_df)} promoter buy transactions.")
        else:
            print("ℹ️ No promoter acquisitions found in today's data.")

    except KeyError as e:
        print(f"❌ Column naming mismatch: {e}")
        print(f"Available columns: {df.columns.tolist()}")

if __name__ == "__main__":
    data = fetch_trendlyne_data()
    process_and_save(data)
