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
            try:
                r = self._scan_ticker(ticker, df)
                if r:
                    results.append(r)
            except Exception:
                continue
        elapsed = time.perf_counter() - start
        logger.info("Scan done in %.2f sec — %d results", elapsed, len(results))
        return results

    def _scan_ticker(self, ticker: str, df: pd.DataFrame) -> dict | None:
        if df is None or len(df) < 200:
            return None

        df.columns = [str(c).lower().replace("adj ", "") for c in df.columns]
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

        # Layer 1 — Liquidity
        fifty_day_idx = max(0, len(close) - 50)
        vol50 = np.mean(volume[fifty_day_idx:])
        if latest_close <= 10 or vol50 <= 500000:
            return None

        # Layer 2 — Uptrend
        ema50 = self._ema(close, 50)
        ema150 = self._ema(close, 150)
        ema200 = self._ema(close, 200)
        if not (latest_close > ema50[-1] and latest_close > ema150[-1] and latest_close > ema200[-1]):
            return None

        # Layer 3 — Near 52-Week High
        year_high = np.max(high[-252:])
        if latest_close < year_high * 0.85:
            return None

        # Layer 4 — VCP Tight Consolidation
        lookback = min(15, len(close))
        recent_high = np.max(high[-lookback:])
        recent_low = np.min(low[-lookback:])
        recent_avg = np.mean(close[-lookback:])
        tightness = (recent_high - recent_low) / recent_avg if recent_avg > 0 else 1
        if tightness >= 0.12:
            return None

        vol_slope = self._linear_slope(volume[-11:-1]) if len(volume) >= 11 else 0
        if vol_slope > 0:
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
            "scan_time": time.strftime("%Y-%m-%d %I:%M %p EST"),
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
    def check_single(ticker: str, df: pd.DataFrame) -> str:
        scanner = QullamaggieScanner({ticker: df})
        results = scanner.scan()
        if not results:
            layers = []
            r = scanner._scan_ticker(ticker, df)
            if r is None:
                layers = scanner._debug_layers(ticker, df)
            return "\n".join(layers) if layers else f"{ticker}: No breakout (failed filter)"
        r = results[0]
        msg = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 BREAKOUT CHECK: {ticker}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price      : ${r['price']}\n"
            f"📊 Vol Ratio  : {r['volume_ratio']}x avg\n"
            f"📈 52W High   : {r['distance_from_52w_high']}%\n"
            f"🎯 Tightness  : {r['consolidation_tightness']}%\n"
            f"⚡ Signal     : {r['signal_strength']}\n"
            f"🔥 EP Alert   : {r['ep_candidate']}\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        return msg

    @staticmethod
    def _debug_layers(ticker: str, df: pd.DataFrame) -> list[str]:
        lines = [f"🔍 {ticker} analysis:"]
        df.columns = [str(c).lower().replace("adj ", "") for c in df.columns]
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values
        latest_close = float(close[-1])
        prev_close = float(close[-2])
        latest_vol = int(volume[-1])

        fifty_day_idx = max(0, len(close) - 50)
        vol50 = np.mean(volume[fifty_day_idx:])

        lines.append(f"  Price=${latest_close:.2f} Vol50={vol50:.0f}")
        if latest_close <= 10:
            lines.append(f"  ❌ Layer 1: Price ${latest_close} <= $10")
        elif vol50 <= 500000:
            lines.append(f"  ❌ Layer 1: Avg vol {vol50:.0f} <= 500k")
        else:
            lines.append(f"  ✅ Layer 1: Liquid")

        ema50 = QullamaggieScanner._ema(close, 50)
        ema150 = QullamaggieScanner._ema(close, 150)
        ema200 = QullamaggieScanner._ema(close, 200)
        if not (latest_close > ema50[-1] and latest_close > ema150[-1] and latest_close > ema200[-1]):
            lines.append(f"  ❌ Layer 2: Close=${latest_close:.2f} not above all EMAs (50={ema50[-1]:.2f}, 150={ema150[-1]:.2f}, 200={ema200[-1]:.2f})")
        else:
            lines.append(f"  ✅ Layer 2: Uptrend (above all EMAs)")

        year_high = np.max(high[-252:])
        pct_of_high = (latest_close / year_high) * 100 if year_high > 0 else 0
        if latest_close < year_high * 0.85:
            lines.append(f"  ❌ Layer 3: ${latest_close} is {pct_of_high:.1f}% of 52w high ${year_high:.2f} (need >=85%)")
        else:
            lines.append(f"  ✅ Layer 3: Near 52w high ({pct_of_high:.1f}%)")

        lookback = min(15, len(close))
        rh = np.max(high[-lookback:])
        rl = np.min(low[-lookback:])
        ra = np.mean(close[-lookback:])
        tightness = (rh - rl) / ra if ra > 0 else 1
        if tightness >= 0.12:
            lines.append(f"  ❌ Layer 4: Tightness {tightness*100:.2f}% >= 12%")
        else:
            lines.append(f"  ✅ Layer 4: Tight consolidation ({tightness*100:.2f}%)")

        vol_slope_val = QullamaggieScanner._linear_slope(volume[-11:-1]) if len(volume) >= 11 else 0
        if vol_slope_val > 0:
            lines.append(f"  ❌ Layer 4b: Volume slope {vol_slope_val:.2f} > 0 (increasing)")
        else:
            lines.append(f"  ✅ Layer 4b: Volume declining ({vol_slope_val:.2f})")

        high10 = np.max(high[-10:-1]) if len(high) >= 10 else np.max(high[:-1])
        pct_chg = (latest_close - prev_close) / prev_close
        if latest_vol < 1.5 * vol50:
            lines.append(f"  ❌ Layer 5a: Vol {latest_vol} < 1.5x avg {vol50:.0f}")
        else:
            lines.append(f"  ✅ Layer 5a: Volume spike ({latest_vol/vol50:.2f}x)")
        if latest_close <= high10:
            lines.append(f"  ❌ Layer 5b: Close ${latest_close:.2f} <= 10d high ${high10:.2f}")
        else:
            lines.append(f"  ✅ Layer 5b: New 10-day high")
        if pct_chg < 0.01:
            lines.append(f"  ❌ Layer 5c: Daily change {pct_chg*100:.2f}% < 1%")
        else:
            lines.append(f"  ✅ Layer 5c: Daily change {pct_chg*100:.2f}%")

        avg_range = np.mean(high[-50:] - low[-50:])
        today_rng = float(high[-1]) - float(low[-1])
        ep = latest_vol > 3 * vol50 and today_rng > 2 * avg_range
        if ep:
            lines.append(f"  🔥 Layer 6: EP CANDIDATE")

        return lines
