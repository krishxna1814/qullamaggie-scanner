import csv
import logging
import os
import re
import time

import requests

UNIVERSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "universe.csv")
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
NASDAQ_API_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0"
NYSE_API_URL = "https://api.nasdaq.com/api/screener/stocks?exchange=nyse&tableonly=true&limit=10000&offset=0"
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


def _parse_market_cap(raw) -> float:
    if raw is None or raw == "" or raw == "N/A":
        return 0.0
    if not isinstance(raw, str):
        return 0.0
    try:
        return float(raw.replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _parse_price(raw) -> float:
    if raw is None or raw == "" or raw == "N/A":
        return 0.0
    if not isinstance(raw, str):
        return 0.0
    try:
        return float(raw.replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _try_fetch_exchange_api_with_prices(url: str = NASDAQ_API_URL, label: str = "NASDAQ") -> list[dict] | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("data", {}).get("table", {}).get("rows", [])
            result = []
            for row in rows:
                symbol = row.get("symbol")
                if not symbol or not isinstance(symbol, str) or not symbol.strip():
                    continue
                symbol = symbol.strip()
                if EXCLUDE_PATTERNS.search(symbol):
                    continue
                lastsale = _parse_price(row.get("lastsale"))
                market_cap = _parse_market_cap(row.get("marketCap"))
                result.append({"symbol": symbol, "lastsale": lastsale, "marketCap": market_cap})
            logger.info("%s API: %d tickers with prices fetched", label, len(result))
            return result
        except Exception as e:
            logger.warning("%s API attempt %d/%d failed: %s", label, attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    return None


def fetch_universe() -> list[str]:
    result = _try_fetch_nasdaq_txt()
    if result is not None:
        logger.info("NASDAQ TXT: %d tickers fetched", len(result))
        return result
    logger.info("NASDAQ TXT failed, trying NASDAQ API...")
    rows = _try_fetch_exchange_api_with_prices()
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
    all_rows = []
    for url, label in [(NASDAQ_API_URL, "NASDAQ"), (NYSE_API_URL, "NYSE")]:
        rows = _try_fetch_exchange_api_with_prices(url, label)
        if rows:
            all_rows.extend(rows)

    if all_rows:
        seen = set()
        deduped = []
        for r in all_rows:
            s = r["symbol"]
            if s not in seen:
                seen.add(s)
                deduped.append(r)
        logger.info("Combined universe: %d unique tickers (NASDAQ+NYSE)", len(deduped))
        return deduped

    logger.info("Exchange APIs failed, trying TXT fallback (covers all exchanges)...")
    tickers = _try_fetch_nasdaq_txt()
    if tickers is not None:
        logger.warning("TXT fallback has no price data — returning symbols only (prices=0)")
        return [{"symbol": t, "lastsale": 0.0, "marketCap": 0.0} for t in tickers]
    cached = load_universe()
    if cached:
        logger.warning("All remote sources failed. Using cached universe.csv (%d tickers) without prices", len(cached))
        return [{"symbol": t, "lastsale": 0.0, "marketCap": 0.0} for t in cached]
    raise RuntimeError("All universe sources failed. No cached universe.csv found.")


def filter_liquid(rows: list[dict], min_price: float = 1.0, min_mcap: float = 100_000_000) -> list[str]:
    passed = [r for r in rows if r["lastsale"] >= min_price and r.get("marketCap", 0) >= min_mcap]
    result = [r["symbol"] for r in passed]
    logger.info("Universe filter: %d/%d passed price>=%s, mcap>=%s", len(result), len(rows), f"${min_price:.0f}", f"${min_mcap:.0f}")
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
