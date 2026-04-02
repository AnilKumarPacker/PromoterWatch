import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import io

async def fetch_insider_data():
    async with async_playwright() as p:
        # Launching a stealthy browser instance
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("🌐 Navigating to Screener.in...")
        try:
            # Screener is currently the most stable data source for this
            await page.goto("https://www.screener.in/insider-trading/", wait_until="networkidle", timeout=60000)
            
            # Wait for the table to appear on the page
            await page.wait_for_selector("table")
            
            # Get the HTML content of the table
            table_html = await page.evaluate("document.querySelector('table').outerHTML")
            
            # Read the HTML into Pandas
            df = pd.read_html(io.StringIO(table_html))[0]
            await browser.close()
            return df
            
        except Exception as e:
            print(f"❌ Playwright Error: {e}")
            await browser.close()
            return pd.DataFrame()

def process_data(df):
    if df.empty:
        print("⚠️ No data fetched.")
        return

    # Standardizing columns
    df.columns = [str(c).strip() for c in df.columns]
    
    # Filtering for 'Buy' or 'Acquisition' in the Description
    # Screener's 2026 layout usually puts details in 'Description' or 'Mode'
    buy_mask = df.astype(str).apply(lambda x: x.str.contains('Buy|Acquisition', case=False)).any(axis=1)
    promoter_mask = df.astype(str).apply(lambda x: x.str.contains('Promoter', case=False)).any(axis=1)
    
    final_report = df[buy_mask & promoter_mask]

    if not final_report.empty:
        final_report.to_csv("insider_report.csv", index=False)
        print(f"✅ Found {len(final_report)} promoter trades. Saved to CSV.")
    else:
        print("ℹ️ No promoter buys found today.")

if __name__ == "__main__":
    data = asyncio.run(fetch_insider_data())
    process_data(data)
