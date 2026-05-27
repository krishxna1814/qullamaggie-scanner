import csv
import re
import requests

NASDAQ_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"

EXCLUDE_PATTERNS = re.compile(
    r"(warrant|unit|right|preferred|notes)",
    re.IGNORECASE
)

def fetch_universe() -> list[str]:
    resp = requests.get(NASDAQ_URL, timeout=30)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    reader = csv.DictReader(lines, delimiter="|")
    tickers = []
    for row in reader:
        if row.get("ETF", "").strip().upper() == "Y":
            continue
        if row.get("Test Issue", "").strip().upper() == "Y":
            continue
        symbol = row.get("Symbol", "").strip()
        if not symbol:
            continue
        if EXCLUDE_PATTERNS.search(symbol):
            continue
        tickers.append(symbol)
    return sorted(set(tickers))

def save_universe(tickers: list[str], path: str = "universe.csv"):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker"])
        for t in tickers:
            writer.writerow([t])

def load_universe(path: str = "universe.csv") -> list[str]:
    with open(path) as f:
        return [row["ticker"] for row in csv.DictReader(f)]
