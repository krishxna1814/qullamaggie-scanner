import logging
import time

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class QullamaggieScanner:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self.data = data

    def scan(self) -> list[dict]:
        start = time.perf_counter()
        results = []
        for ticker, df in self.data.items():
            r = self._scan_ticker(ticker, df)
            if r:
                results.append(r)
        elapsed = time.perf_counter() - start
        logger.info("Scan completed in %.2f seconds — %d results", elapsed, len(results))
        return results

    def _scan_ticker(self, ticker: str, df: pd.DataFrame) -> dict | None:
        if df is None or len(df) < 200:
            return None

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

        try:
            latest_close = float(close[-1])
            latest_high = float(high[-1])
            latest_low = float(low[-1])
            latest_vol = int(volume[-1])
            prev_close = float(close[-2])
        except (IndexError, ValueError):
            return None

        # Layer 1 — Basic Liquidity
        fifty_day_idx = max(0, len(close) - 50)
        vol50 = np.mean(volume[fifty_day_idx:])
        if latest_close <= 10 or vol50 <= 500000:
            return None

        # Layer 2 — Uptrend Filter
        ema50 = self._ema(close, 50)
        ema150 = self._ema(close, 150)
        ema200 = self._ema(close, 200)
        if not (latest_close > ema50[-1] and latest_close > ema150[-1] and latest_close > ema200[-1]):
            return None

        # Layer 3 — Near 52-Week High
        year_high = np.max(high[-252:])
        if latest_close < year_high * 0.85:
            return None

        # Layer 4 — Tight Consolidation VCP-style
        lookback = min(15, len(close))
        recent_high = np.max(high[-lookback:])
        recent_low = np.min(low[-lookback:])
        recent_avg = np.mean(close[-lookback:])
        tightness = (recent_high - recent_low) / recent_avg if recent_avg > 0 else 1
        if tightness >= 0.12:
            return None

        vol_slope = self._linear_slope(volume[-10:])
        if vol_slope > 0 and len(volume) >= 10:
            return None

        # Layer 5 — Breakout Trigger
        high10 = np.max(high[-10:-1]) if len(high) >= 10 else np.max(high[:-1])
        if latest_vol < 1.5 * vol50:
            return None
        if latest_close <= high10:
            return None
        pct_change = (latest_close - prev_close) / prev_close
        if pct_change < 0.01:
            return None

        # Layer 6 — Episodic Pivot Check
        avg_range = np.mean(high[-50:] - low[-50:])
        today_range = latest_high - latest_low
        ep_candidate = bool(latest_vol > 3 * vol50 and today_range > 2 * avg_range)

        vol_ratio = round(latest_vol / vol50, 2)
        distance_from_52w = round((1 - (year_high - latest_close) / year_high) * 100, 2) if year_high > 0 else 100
        signal_strength = "STRONG" if vol_ratio > 2.5 else "NORMAL"

        return {
            "ticker": ticker,
            "price": round(latest_close, 2),
            "volume_ratio": vol_ratio,
            "distance_from_52w_high": distance_from_52w,
            "consolidation_tightness": round(tightness * 100, 2),
            "ep_candidate": ep_candidate,
            "signal_strength": signal_strength,
        }

    @staticmethod
    def _ema(values: np.ndarray, period: int) -> np.ndarray:
        if len(values) < period:
            return values[-1:] if len(values) > 0 else np.array([0])
        out = np.full(len(values), np.nan)
        alpha = 2 / (period + 1)
        out[period - 1] = np.mean(values[:period])
        for i in range(period, len(values)):
            out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
        return out

    @staticmethod
    def _linear_slope(y: np.ndarray) -> float:
        n = len(y)
        if n < 2:
            return 0.0
        x = np.arange(n)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x)**2)
        return slope

    @staticmethod
    def analyze_sectors(sector_data: dict[str, pd.DataFrame]) -> dict:
        sector_map = {
            "XLF": "Financials", "XLK": "Technology", "XLV": "Healthcare",
            "XLI": "Industrials", "XLB": "Materials", "XLE": "Energy",
            "XLU": "Utilities", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
            "XLC": "Communication", "XLRE": "Real Estate"
        }
        results = {}
        for ticker, df in sector_data.items():
            if df is None or len(df) < 200:
                continue
            close = df["close"].values
            if len(close) < 2:
                continue

            latest_close = float(close[-1])

            ema50 = QullamaggieScanner._ema(close, 50)
            ema200 = QullamaggieScanner._ema(close, 200)

            uptrend = latest_close > ema50[-1] and latest_close > ema200[-1]

            year_high = np.max(df["high"].values[-252:])
            year_low = np.min(df["low"].values[-252:])
            pct_from_low = round((latest_close - year_low) / year_low * 100, 1) if year_low > 0 else 0
            near_high = "NEW HIGH" if latest_close >= year_high * 0.99 else (
                f"{round((latest_close / year_high) * 100, 1)}%"
            )

            name = sector_map.get(ticker, ticker)
            results[ticker] = {
                "name": name,
                "uptrend": uptrend,
                "pct_from_52w_low": pct_from_low,
                "near_52w_high": near_high,
                "price": latest_close,
            }
        return results
