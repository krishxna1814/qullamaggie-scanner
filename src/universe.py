import csv
import logging
import os
import re
import time

import requests

UNIVERSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "universe.csv")
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
        logger.info("NASDAQ TXT: %d tickers fetched", len(result))
        return result
    logger.info("NASDAQ TXT failed, trying NASDAQ API...")
    result = _try_fetch_nasdaq_api()
    if result is not None:
        logger.info("NASDAQ API: %d tickers fetched", len(result))
        return result
    cached = load_universe()
    if cached:
        logger.warning("All remote sources failed. Using cached universe.csv (%d tickers)", len(cached))
        return cached
    raise RuntimeError("All universe sources failed. No cached universe.csv found.")


def save_universe(tickers: list[str], path: str = UNIVERSE_PATH):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker"])
        for t in tickers:
            writer.writerow([t])
    logger.info("Universe saved to %s (%d tickers)", path, len(tickers))


def load_universe(path: str = UNIVERSE_PATH) -> list[str]:
    try:
        with open(path) as f:
            return [row["ticker"] for row in csv.DictReader(f)]
    except (FileNotFoundError, KeyError):
        return []



