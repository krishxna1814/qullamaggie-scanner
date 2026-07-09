import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

import pandas as pd
import yfinance as yf

CHUNK_SIZE = 50
SLEEP_BETWEEN_CHUNKS = 2
YF_TIMEOUT = 30
MIN_DATA_POINTS = 3  # Reduced from 5 to support shorter periods like 6mo

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
    def __init__(self, chunk_size: int = CHUNK_SIZE, min_data_points: int = MIN_DATA_POINTS):
        self.chunk_size = chunk_size
        self.min_data_points = min_data_points

    def fetch_by_period(self, tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
        logger.info("Fetch: %d tickers, %s data", len(tickers), period)
        return self._fetch_in_chunks(tickers, period, "1d")

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

    def _parse_chunk(self, data) -> dict[str, pd.DataFrame]:
        result = {}
        if data is None or not hasattr(data, "columns") or data.empty:
            return result
        if not isinstance(data.columns, pd.MultiIndex):
            tdf = data.dropna(how="all")
            if not tdf.empty and len(tdf) >= self.min_data_points:
                tdf.columns = [str(c).lower() for c in tdf.columns]
                result["UNKNOWN"] = tdf
            return result

        l0 = list(data.columns.get_level_values(0).unique())
        l1 = list(data.columns.get_level_values(1).unique())

        def _has_ticker(vals):
            return sum(1 for v in vals if isinstance(v, str) and v.isupper() and len(v) <= 10)

        ticker_lvl = 0 if _has_ticker(l0) >= _has_ticker(l1) else 1
        tickers_in = data.columns.get_level_values(ticker_lvl).unique()

        for t in tickers_in:
            if not isinstance(t, str) or not t.isupper():
                continue
            try:
                tdf = data.xs(t, axis=1, level=ticker_lvl).dropna(how="all")
                if tdf.empty or len(tdf) < self.min_data_points:
                    logger.debug(f"Insufficient data points for {t}: {len(tdf)} rows (min required: {self.min_data_points})")
                    continue
                tdf.columns = [str(c).lower() for c in tdf.columns]
                result[t.upper()] = tdf
            except Exception:
                continue
        return result

    def fetch_single(self, ticker: str, period: str = "6mo") -> pd.DataFrame | None:
        try:
            data = yf.download(tickers=ticker, period=period, interval="1d", auto_adjust=True, threads=True, progress=False)
            if not hasattr(data, "columns") or data.empty:
                return None
            parsed = self._parse_chunk(data)
            return parsed.get(ticker.upper())
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            return None
