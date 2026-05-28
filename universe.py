import csv
import json
import re
import time
import logging

import requests

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
NASDAQ_API_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0"

EXCLUDE_PATTERNS = re.compile(r"(warrant|unit|right|preferred|notes)", re.IGNORECASE)
MAX_RETRIES = 3
TIMEOUT = 60

logger = logging.getLogger(__name__)


def _try_fetch_nasdaq_txt() -> list[str] | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(NASDAQ_URL, timeout=TIMEOUT, headers=headers)
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
        except Exception as e:
            logger.warning("NASDAQ TXT attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    return None


def _try_fetch_nasdaq_api() -> list[str] | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(NASDAQ_API_URL, timeout=TIMEOUT, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("data", {}).get("table", {}).get("rows", [])
            tickers = []
            for row in rows:
                symbol = row.get("symbol", "").strip()
                if not symbol:
                    continue
                if EXCLUDE_PATTERNS.search(symbol):
                    continue
                tickers.append(symbol)
            return sorted(set(tickers))
        except Exception as e:
            logger.warning("NASDAQ API attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    return None


def fetch_universe() -> list[str]:
    result = _try_fetch_nasdaq_txt()
    if result is not None:
        return result
    logger.info("NASDAQ TXT failed, trying NASDAQ API...")
    result = _try_fetch_nasdaq_api()
    if result is not None:
        return result
    raise RuntimeError("All universe sources failed. NASDAQ TXT and API both unreachable.")


def save_universe(tickers: list[str], path: str = "universe.csv"):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker"])
        for t in tickers:
            writer.writerow([t])


def load_universe(path: str = "universe.csv") -> list[str]:
    with open(path) as f:
        return [row["ticker"] for row in csv.DictReader(f)]
