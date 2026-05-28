import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import pandas as pd
import yfinance as yf

CHUNK_SIZE = 50
SLEEP_BETWEEN_CHUNKS = 3
YF_TIMEOUT = 180

logger = logging.getLogger(__name__)


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
            raise TimeoutError(f"yfinance download timed out after {timeout}s for chunk of {len(tickers)} tickers")


class SmartFetcher:
    def __init__(self, chunk_size: int = CHUNK_SIZE):
        self.chunk_size = chunk_size

    def eod_fetch(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        logger.info("EOD fetch: %d tickers, 6 months data", len(tickers))
        return self._fetch_in_chunks(tickers, "6mo", "1d")

    def intraday_fetch(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        logger.info("Intraday fetch: %d tickers, 5 days data", len(tickers))
        return self._fetch_in_chunks(tickers, "5d", "1d", timeout=120)

    def weekly_fetch(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        logger.info("Weekly fetch: %d tickers, 1 year data", len(tickers))
        return self._fetch_in_chunks(tickers, "1y", "1d")

    def _fetch_in_chunks(self, tickers: list[str], period: str, interval: str, timeout: int = YF_TIMEOUT) -> dict[str, pd.DataFrame]:
        start = time.perf_counter()
        chunks = [tickers[i:i+self.chunk_size] for i in range(0, len(tickers), self.chunk_size)]
        result = {}
        for idx, chunk in enumerate(chunks, 1):
            try:
                data = _yf_download_with_timeout(chunk, period, interval, timeout)
                parsed = self._parse_chunk(data)
                result.update(parsed)
                logger.info("Fetched chunk %d/%d: %d tickers", idx, len(chunks), len(parsed))
            except Exception as e:
                logger.warning("Chunk %d/%d failed: %s", idx, len(chunks), e)
            time.sleep(SLEEP_BETWEEN_CHUNKS)
        elapsed = time.perf_counter() - start
        logger.info("Fetched %d stocks in %.1f seconds", len(result), elapsed)
        return result

    def _parse_chunk(self, data: pd.DataFrame) -> dict[str, pd.DataFrame]:
        result = {}
        if data.empty:
            return result
        if isinstance(data.columns, pd.MultiIndex):
            tickers_in = data.columns.get_level_values(1).unique()
            for t in tickers_in:
                try:
                    tdf = data.xs(t, axis=1, level=1).dropna(how="all")
                    if tdf.empty or len(tdf) < 5:
                        continue
                    tdf.columns = [c.lower() for c in tdf.columns]
                    result[t.upper()] = tdf
                except Exception:
                    continue
        else:
            ticker = "UNKNOWN"
            tdf = data.dropna(how="all")
            if not tdf.empty and len(tdf) >= 5:
                tdf.columns = [c.lower() for c in tdf.columns]
                result[ticker] = tdf
        return result

    def fetch_single(self, ticker: str) -> pd.DataFrame | None:
        try:
            data = yf.download(tickers=ticker, period="1y", interval="1d", auto_adjust=True, threads=True, progress=False)
            if data.empty:
                return None
            parsed = self._parse_chunk(data)
            return parsed.get(ticker.upper())
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            return None
