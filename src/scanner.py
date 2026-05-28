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
        results = self._candidates[:keep]

        for r in results:
            r["rank"] = results.index(r) + 1

        elapsed = time.perf_counter() - start
        logger.info("Scan done in %.2f sec — %d candidates, kept top %d (%.1f%%)",
                     elapsed, len(self._candidates), len(results), top_pct)
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

        avg_volume = int(np.mean(volume))
        if avg_volume < 1_000_000:
            return None

        daily_ranges = (high - low) / close
        adr = float(np.mean(daily_ranges))
        if adr < 0.03:
            return None

        first_close = float(close[0])
        total_return = (latest_close - first_close) / first_close

        return {
            "ticker": ticker,
            "price": round(latest_close, 2),
            "avg_volume": avg_volume,
            "adr": round(adr * 100, 2),
            "total_return": round(total_return * 100, 2),
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
            f"📈 Return     : {r['total_return']}%\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        return msg
