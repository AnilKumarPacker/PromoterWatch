"""
promoter_watch.py
─────────────────
Weekly NSE/BSE Promoter Buying Report
Runs on GitHub Actions → saves HTML report to Google Drive →
Google Drive desktop app syncs it to your Windows PC automatically.

SETUP:
  pip install requests beautifulsoup4 anthropic google-api-python-client
              google-auth-httplib2 google-auth-oauthlib

REQUIRED SECRETS (set in GitHub Actions → Settings → Secrets):
  ANTHROPIC_API_KEY      your Claude API key
  GDRIVE_FOLDER_ID       ID of the Google Drive folder to save reports into
  GDRIVE_CREDENTIALS     contents of your service account credentials JSON
"""

import os
import sys
import json
import logging
import argparse
import io
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
import anthropic
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account

# ─────────────────────────────────────────────
# CONFIG — all read from environment variables
# (set these as GitHub Actions secrets)
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
GDRIVE_FOLDER_ID   = os.environ.get("GDRIVE_FOLDER_ID", "")   # see setup guide
GDRIVE_CREDENTIALS = os.environ.get("GDRIVE_CREDENTIALS", "") # JSON string

LOOKBACK_DAYS = 7
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TRENDLYNE_URL = "https://trendlyne.com/equity/group-insider-trading-sast/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── 1. FETCH ──────────────────────────────────────────────────────────────────

def fetch_insider_trades() -> list[dict]:
    log.info("Fetching insider trades from Trendlyne...")
    try:
        resp = requests.get(TRENDLYNE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Fetch failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("No table found — site structure may have changed.")
        return []

    rows = []
    headers_row = table.find("tr")
    col_names = [th.get_text(strip=True) for th in headers_row.find_all(["th", "td"])]
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) >= len(col_names):
            rows.append(dict(zip(col_names, cells)))

    log.info("Fetched %d raw rows.", len(rows))
    return rows


# ── 2. FILTER ─────────────────────────────────────────────────────────────────

PROMOTER_KEYWORDS = {"promoter", "promoter group", "promoter & director"}
BUY_KEYWORDS      = {"acquisition", "buy", "market purchase"}
EXCLUDE_MODES     = {"pledge", "inter-se transfer", "allotment", "rights issue",
                     "depledge", "invoke", "revoke", "inheritance"}

def is_promoter_buy(row: dict) -> bool:
    category = row.get("Client Category", "").lower()
    action   = row.get("Action*", row.get("Action", "")).lower()
    mode     = row.get("Mode", "").lower()
    reg      = row.get("Regulation (Insider/SAST)", "").lower()
    if not any(k in category for k in PROMOTER_KEYWORDS):
        return False
    if any(k in mode for k in EXCLUDE_MODES):
        return False
    if "sast (reg31)" in reg:
        return False
    if not any(k in action for k in BUY_KEYWORDS):
        return False
    return True

def within_lookback(row: dict, days: int) -> bool:
    date_str = row.get("Reported To/By Exchange", "")
    for fmt in ("%d %b %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(
                date_str.split()[0] + " " + " ".join(date_str.split()[1:3]), fmt
            )
            return dt >= datetime.now() - timedelta(days=days)
        except (ValueError, IndexError):
            continue
    return True

def filter_promoter_buys(rows: list[dict]) -> list[dict]:
    filtered = [r for r in rows if is_promoter_buy(r) and within_lookback(r, LOOKBACK_DAYS)]
    log.info("Filtered to %d promoter buy rows.", len(filtered))
    return filtered


# ── 3. ANALYSE WITH CLAUDE ────────────────────────────────────────────────────

def analyse_with_claude(rows: list[dict]) -> str:
    if not rows:
        return "<p>No promoter buying activity found this week.</p>"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""You are an Indian equity market analyst assistant.

Below is this week's NSE/BSE insider trading data filtered to show ONLY promoter market purchases.

Your task:
1. Identify high-conviction signals where:
   - Multiple promoters are buying the same stock
   - The quantity or value is significant
   - A promoter & director is personally buying
2. Group entries by stock name
3. Return ONLY a clean HTML snippet (no <html>/<body> tags) with:
   - A summary paragraph (2-3 sentences)
   - An HTML table: Stock | Promoter | Qty | Avg Price (Rs) | Date | Signal Strength
   - Signal Strength: High / Medium / Low
   - A "Key observations" bullet list at the end (max 5 bullets)

Data:
{json.dumps(rows, indent=2)}
"""

    log.info("Calling Claude API...")
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ── 4. BUILD HTML REPORT ──────────────────────────────────────────────────────

def build_html_report(analysis_html: str, row_count: int) -> str:
    today      = datetime.now().strftime("%d %b %Y")
    week_start = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%d %b")
    generated  = datetime.now().strftime("%d %b %Y, %I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Promoter Watch {today}</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:"Segoe UI",Arial,sans-serif; font-size:14px;
            background:#f0f2f5; color:#1a1a2e; padding:32px 16px; }}
    .card {{ background:#fff; border-radius:12px; padding:32px 36px;
             max-width:1000px; margin:0 auto;
             box-shadow:0 2px 12px rgba(0,0,0,.08); }}
    .header {{ display:flex; justify-content:space-between;
               align-items:flex-start; margin-bottom:24px;
               padding-bottom:20px; border-bottom:2px solid #f0f2f5; }}
    h1 {{ font-size:22px; color:#1a1a2e; margin-bottom:6px; }}
    .meta {{ color:#888; font-size:12px; }}
    .badge {{ background:#e8f5e9; color:#2e7d32; border-radius:20px;
              padding:5px 16px; font-size:12px; font-weight:600; }}
    table {{ width:100%; border-collapse:collapse; margin:20px 0; font-size:13px; }}
    th {{ background:#1a1a2e; color:#fff; padding:11px 14px; text-align:left; font-weight:500; }}
    th:first-child {{ border-radius:8px 0 0 0; }}
    th:last-child  {{ border-radius:0 8px 0 0; }}
    td {{ padding:9px 14px; border-bottom:1px solid #f0f2f5; vertical-align:top; }}
    tr:last-child td {{ border-bottom:none; }}
    tr:hover td {{ background:#fafbfc; }}
    .high   {{ color:#c62828; font-weight:600; }}
    .medium {{ color:#e65100; font-weight:600; }}
    .low    {{ color:#777; font-weight:500; }}
    p  {{ line-height:1.75; margin-bottom:14px; color:#333; }}
    ul {{ margin:8px 0 16px 22px; }}
    li {{ margin-bottom:7px; line-height:1.65; color:#333; }}
    h2,h3 {{ margin:22px 0 10px; font-size:16px; color:#1a1a2e; font-weight:600; }}
    .footer {{ margin-top:28px; padding-top:16px; border-top:1px solid #f0f2f5;
               color:#aaa; font-size:11px; text-align:center; line-height:1.8; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div>
        <h1>&#x1F4C8; Weekly Promoter Buying Report</h1>
        <div class="meta">Period: {week_start} &ndash; {today} &bull; Generated: {generated}</div>
      </div>
      <div class="badge">{row_count} purchase(s) found</div>
    </div>
    {analysis_html}
    <div class="footer">
      Data: Trendlyne (SEBI PIT / SAST disclosures) &bull; Auto-saved via GitHub Actions<br>
      &#9888; For informational purposes only. Not investment advice.
    </div>
  </div>
</body>
</html>"""


# ── 5. SAVE TO GOOGLE DRIVE ───────────────────────────────────────────────────

def get_drive_service():
    """Build a Google Drive API service using service account credentials."""
    creds_info = json.loads(GDRIVE_CREDENTIALS)
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def save_to_gdrive(html_content: str) -> str:
    """Upload the HTML report to Google Drive, return the file URL."""
    filename = f"promoter_watch_{datetime.now().strftime('%Y-%m-%d')}.html"
    log.info("Uploading %s to Google Drive folder %s...", filename, GDRIVE_FOLDER_ID)

    service = get_drive_service()

    file_metadata = {
        "name": filename,
        "parents": [GDRIVE_FOLDER_ID],
        "mimeType": "text/html",
    }
    media = MediaIoBaseUpload(
        io.BytesIO(html_content.encode("utf-8")),
        mimetype="text/html",
        resumable=False,
    )
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink",
    ).execute()

    link = uploaded.get("webViewLink", "")
    log.info("Uploaded: %s  |  Link: %s", uploaded.get("name"), link)
    return link


# ── 6. MAIN RUN ───────────────────────────────────────────────────────────────

def run_report():
    log.info("=== Promoter Watch — starting run ===")
    raw_rows      = fetch_insider_trades()
    promoter_buys = filter_promoter_buys(raw_rows)
    analysis_html = analyse_with_claude(promoter_buys)
    html_content  = build_html_report(analysis_html, len(promoter_buys))
    link          = save_to_gdrive(html_content)
    log.info("=== Done. File syncs to your PC via Google Drive desktop app ===")
    if link:
        log.info("View online: %s", link)


if __name__ == "__main__":
    run_report()
