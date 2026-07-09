import logging
import time

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Sector mapping for major stocks
STOCK_SECTOR_MAP = {
    # Technology
    "NVDA": "Technology", "AAPL": "Technology", "GOOGL": "Technology", "MSFT": "Technology",
    "META": "Technology", "AMZN": "Technology", "NFLX": "Technology", "INTC": "Technology",
    "AMD": "Technology", "ADBE": "Technology", "CRM": "Technology", "NOW": "Technology",
    "SNOW": "Technology", "DDOG": "Technology", "NET": "Technology", "OKTA": "Technology",
    "DASH": "Technology", "CRWD": "Technology", "PANW": "Technology", "ANET": "Technology",
    "COIN": "Technology", "RBLX": "Technology", "SHOP": "Technology", "TSM": "Technology",
    "ASML": "Technology", "QCOM": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "MU": "Technology", "MRVL": "Technology", "STX": "Technology", "WDC": "Technology",
    "MCHP": "Technology", "ADI": "Technology", "AVGO": "Technology", "NXPI": "Technology",
    
    # Financials
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials", "GS": "Financials",
    "MS": "Financials", "BLK": "Financials", "SCHW": "Financials", "IBKR": "Financials",
    "CME": "Financials", "ICE": "Financials", "CBOE": "Financials", "V": "Financials",
    "MA": "Financials", "AXP": "Financials", "COF": "Financials", "PNC": "Financials",
    "USB": "Financials", "TD": "Financials", "BMO": "Financials", "RY": "Financials",
    
    # Healthcare
    "LLY": "Healthcare", "JNJ": "Healthcare", "UNH": "Healthcare", "MRK": "Healthcare",
    "PFE": "Healthcare", "ABBV": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "DHR": "Healthcare", "MDT": "Healthcare", "GILD": "Healthcare", "BIIB": "Healthcare",
    "VRTX": "Healthcare", "SYK": "Healthcare", "BMY": "Healthcare", "AMGN": "Healthcare",
    "REGN": "Healthcare", "ILMN": "Healthcare", "MRNA": "Healthcare", "BNTX": "Healthcare",
    
    # Industrials
    "BA": "Industrials", "CAT": "Industrials", "GE": "Industrials", "HON": "Industrials",
    "RTX": "Industrials", "LMT": "Industrials", "NOC": "Industrials", "GD": "Industrials",
    "ETN": "Industrials", "EMR": "Industrials", "ITW": "Industrials", "PCAR": "Industrials",
    "ROK": "Industrials", "TDG": "Industrials", "DOV": "Industrials", "XYL": "Industrials",
    
    # Consumer Discretionary
    "MCD": "Consumer Discretionary", "SBUX": "Consumer Discretionary", "NKE": "Consumer Discretionary",
    "YUM": "Consumer Discretionary", "CMG": "Consumer Discretionary", "DIS": "Consumer Discretionary",
    "TJX": "Consumer Discretionary", "HD": "Consumer Discretionary", "LOW": "Consumer Discretionary",
    "ROST": "Consumer Discretionary", "RCL": "Consumer Discretionary", "LVS": "Consumer Discretionary",
    "BKNG": "Consumer Discretionary", "EXPE": "Consumer Discretionary", "MAR": "Consumer Discretionary",
    
    # Consumer Staples
    "WMT": "Consumer Staples", "PG": "Consumer Staples", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "MO": "Consumer Staples", "PM": "Consumer Staples",
    "COST": "Consumer Staples", "CL": "Consumer Staples", "KMB": "Consumer Staples",
    "GIS": "Consumer Staples", "KR": "Consumer Staples", "SYY": "Consumer Staples",
    
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    "OXY": "Energy", "MPC": "Energy", "VLO": "Energy", "PSX": "Energy",
    "EOG": "Energy", "MRO": "Energy", "DVN": "Energy", "OKE": "Energy",
    
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities", "EXC": "Utilities",
    "AEP": "Utilities", "XEL": "Utilities", "WEC": "Utilities",
    
    # Real Estate
    "PLD": "Real Estate", "AMT": "Real Estate", "CCI": "Real Estate", "PSA": "Real Estate",
    "EQIX": "Real Estate", "O": "Real Estate", "SPG": "Real Estate",
    
    # Materials
    "LIN": "Materials", "ALB": "Materials", "FCX": "Materials", "NEM": "Materials",
    "RIO": "Materials", "BHP": "Materials", "VALE": "Materials",
}


class Scanner:
    def __init__(self, data: dict[str, pd.DataFrame]):
        self.data = data
        self._candidates = []

    def _get_sector(self, ticker: str) -> str:
        """Get sector for a ticker"""
        return STOCK_SECTOR_MAP.get(ticker.upper(), "Other")

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
        sector = self._get_sector(ticker)

        return {
            "ticker": ticker,
            "sector": sector,
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
        
        sector_emojis = {
            "Technology": "💻",
            "Healthcare": "🏥",
            "Financials": "💰",
            "Industrials": "🏭",
            "Energy": "⚡",
            "Consumer Discretionary": "🛍️",
            "Consumer Staples": "🛒",
            "Real Estate": "🏢",
            "Materials": "🪨",
            "Utilities": "⚙️",
            "Other": "📊",
        }
        sector_emoji = sector_emojis.get(r.get("sector", "Other"), "📊")
        
        msg = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔍 CHECK: {ticker}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{sector_emoji} Sector    : {r.get('sector', 'Unknown')}\n"
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
