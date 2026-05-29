import logging
import time

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self.data = data
        self._candidates = []

    def scan(self, top_pct: float = 3.0) -> list[dict]:
        start = time.perf_counter()
        self._candidates = []
        for ticker, df in self.data.items():
            try:
                r = self._evaluate(ticker, df)
                if r:
                    self._candidates.append(r)
            except Exception:
                continue

        self._candidates.sort(key=lambda r: r["total_return"], reverse=True)
        keep = max(1, int(len(self._candidates) * top_pct / 100))
        top = self._candidates[:keep]

        results = [r for r in top if r["avg_volume"] >= 1_000_000 and r["adr"] >= 3.0 and r["rsi"] > 50]

        for i, r in enumerate(results):
            r["rank"] = i + 1

        elapsed = time.perf_counter() - start
        logger.info("Scan done in %.2f sec — %d candidates, top %d by return, %d passed filters",
                     elapsed, len(self._candidates), keep, len(results))
        return results

    def _evaluate(self, ticker: str, df: pd.DataFrame) -> dict | None:
        if df is None or df.empty or len(df) < 5:
            return None

        df.columns = [str(c).lower().replace("adj ", "") for c in df.columns]
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

        try:
            latest_close = float(close[-1])
        except (IndexError, ValueError):
            return None

        first_close = float(close[0])
        total_return = (latest_close - first_close) / first_close
        avg_volume = int(np.mean(volume))
        daily_ranges = (high - low) / close
        adr = float(np.mean(daily_ranges))
        rsi = self._rsi(close)

        return {
            "ticker": ticker,
            "price": round(latest_close, 2),
            "avg_volume": avg_volume,
            "adr": round(adr * 100, 2),
            "total_return": round(total_return * 100, 2),
            "rsi": round(rsi, 1),
        }

    @staticmethod
    def check_single(ticker: str, df: pd.DataFrame) -> str:
        scanner = Scanner({ticker: df})
        results = scanner.scan(top_pct=100)
        if not results:
            return f"{ticker}: No data"
        r = results[0]
        msg = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 CHECK: {ticker}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price      : ${r['price']}\n"
            f"📊 Avg Vol    : {r['avg_volume']:,}\n"
            f"📈 ADR        : {r['adr']}%\n"
            f"📈 RSI        : {r['rsi']}\n"
            f"📈 Return     : {r['total_return']}%\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        return msg

    @staticmethod
    def _rsi(values, period=14):
        if len(values) < period + 1:
            return 50.0
        deltas = np.diff(values)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
