import csv
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import pandas as pd
import requests
import yfinance as yf

UNIVERSE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "universe.csv")
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
NASDAQ_API_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0"
EXCLUDE_PATTERNS = re.compile(r"(warrant|unit|right|preferred|notes)", re.IGNORECASE)
MAX_RETRIES = 3
TIMEOUT = 60
CHUNK_SIZE = 100
YF_TIMEOUT = 120

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


def _yf_download_with_timeout(tickers, period, interval, timeout=YF_TIMEOUT):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            yf.download,
            tickers=tickers,
            period=period,
            interval=interval,
            auto_adjust=True,
            threads=True,
            progress=False,
            group_by="ticker",
        )
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            raise TimeoutError(f"yfinance download timed out after {timeout}s")


def pre_filter(tickers: list[str], min_price: float = 10.0, min_volume: int = 300000) -> list[str]:
    logger.info("Pre-filtering %d tickers — downloading 5d data...", len(tickers))
    chunks = [tickers[i:i+CHUNK_SIZE] for i in range(0, len(tickers), CHUNK_SIZE)]
    candidates = []
    for idx, chunk in enumerate(chunks, 1):
        try:
            data = _yf_download_with_timeout(chunk, "5d", "1d")
            passed = _extract_candidates(data, min_price, min_volume)
            candidates.extend(passed)
            logger.info("Pre-filter chunk %d/%d: %d candidates from %d tickers", idx, len(chunks), len(passed), len(chunk))
        except Exception as e:
            logger.warning("Pre-filter chunk %d/%d failed: %s", idx, len(chunks), e)
        time.sleep(1)
    logger.info("Pre-filter complete: %d candidates from %d tickers", len(candidates), len(tickers))
    return candidates


def _extract_candidates(data: pd.DataFrame, min_price: float, min_volume: int) -> list[str]:
    if data.empty:
        return []
    if isinstance(data.columns, pd.MultiIndex):
        tickers_in = data.columns.get_level_values(1).unique()
        passed = []
        for t in tickers_in:
            try:
                tdf = data.xs(t, axis=1, level=1).dropna(how="all")
                if tdf.empty:
                    continue
                last = tdf.iloc[-1]
                close = last.get("Close", 0)
                volume = last.get("Volume", 0)
                if close > min_price and volume > min_volume:
                    passed.append(t.upper())
            except Exception:
                continue
        return passed
    try:
        last = data.iloc[-1]
        close = last.get("Close", 0)
        volume = last.get("Volume", 0)
        if close > min_price and volume > min_volume:
            return ["UNKNOWN"]
    except Exception:
        pass
    return []
