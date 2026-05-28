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


def _try_fetch_nasdaq_api_with_prices() -> list[dict] | None:
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
            result = []
            for row in rows:
                symbol = row.get("symbol", "").strip()
                if not symbol:
                    continue
                if EXCLUDE_PATTERNS.search(symbol):
                    continue
                try:
                    lastsale = float(row.get("lastsale", "0").replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    lastsale = 0.0
                try:
                    volume = int(row.get("volume", "0").replace(",", ""))
                except (ValueError, TypeError):
                    volume = 0
                result.append({"symbol": symbol, "lastsale": lastsale, "volume": volume})
            return result
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
    rows = _try_fetch_nasdaq_api_with_prices()
    if rows is not None:
        tickers = sorted(set(r["symbol"] for r in rows))
        logger.info("NASDAQ API: %d tickers fetched", len(tickers))
        return tickers
    cached = load_universe()
    if cached:
        logger.warning("All remote sources failed. Using cached universe.csv (%d tickers)", len(cached))
        return cached
    raise RuntimeError("All universe sources failed. No cached universe.csv found.")


def fetch_universe_with_prices() -> list[dict]:
    rows = _try_fetch_nasdaq_api_with_prices()
    if rows is not None:
        logger.info("NASDAQ API: %d tickers with prices fetched", len(rows))
        return rows
    logger.info("NASDAQ API failed, trying TXT fallback...")
    tickers = _try_fetch_nasdaq_txt()
    if tickers is not None:
        logger.warning("NASDAQ TXT has no price data — returning symbols only (prices=0)")
        return [{"symbol": t, "lastsale": 0.0, "volume": 0} for t in tickers]
    cached = load_universe()
    if cached:
        logger.warning("All remote sources failed. Using cached universe.csv (%d tickers) without prices", len(cached))
        return [{"symbol": t, "lastsale": 0.0, "volume": 0} for t in cached]
    raise RuntimeError("All universe sources failed. No cached universe.csv found.")


def filter_liquid(rows: list[dict], min_price: float = 10.0, min_volume: int = 300000, max_count: int = 500) -> list[str]:
    passed = [r for r in rows if r["lastsale"] >= min_price and r["volume"] >= min_volume]
    passed.sort(key=lambda r: r["volume"], reverse=True)
    result = [r["symbol"] for r in passed[:max_count]]
    logger.info("Liquidity filter: %d/%d passed (top %d by volume)", len(passed), len(rows), len(result))
    return result


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
