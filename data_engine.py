import sqlite3
import logging
import time

import pandas as pd
import yfinance as yf

CHUNK_SIZE = 100
SLEEP_BETWEEN_CHUNKS = 2

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_data (
    ticker TEXT,
    date TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    PRIMARY KEY (ticker, date)
)
"""

class StockDataEngine:
    def __init__(self, db_path: str = "stocks.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def bulk_download(self, tickers: list[str]):
        conn = self._conn()
        total = len(tickers)
        chunks = [tickers[i:i+CHUNK_SIZE] for i in range(0, total, CHUNK_SIZE)]
        failed = []
        for idx, chunk in enumerate(chunks, 1):
            try:
                data = yf.download(
                    tickers=chunk,
                    period="1y",
                    interval="1d",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                    group_by="ticker"
                )
                self._store_chunk(conn, data)
                logger.info("Chunk %d/%d done", idx, len(chunks))
            except Exception as e:
                failed.extend(chunk)
                logger.warning("Chunk %d/%d failed: %s", idx, len(chunks), e)
            time.sleep(SLEEP_BETWEEN_CHUNKS)
        conn.close()
        self._log_failed(failed)
        return failed

    def _store_chunk(self, conn, data: pd.DataFrame):
        if data.empty:
            return
        if isinstance(data.columns, pd.MultiIndex):
            tickers_in_chunk = data.columns.get_level_values(1).unique()
            for ticker in tickers_in_chunk:
                try:
                    tdf = data.xs(ticker, axis=1, level=1).dropna(how="all")
                    if tdf.empty:
                        continue
                    rows = []
                    for date, row in tdf.iterrows():
                        rows.append((
                            ticker.upper(),
                            date.strftime("%Y-%m-%d"),
                            row.get("Open", None),
                            row.get("High", None),
                            row.get("Low", None),
                            row.get("Close", None),
                            int(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else 0,
                        ))
                    conn.executemany(
                        "INSERT OR REPLACE INTO daily_data VALUES (?,?,?,?,?,?,?)",
                        rows
                    )
                    conn.commit()
                except Exception:
                    continue
        else:
            ticker = "UNKNOWN"
            rows = []
            for date, row in data.iterrows():
                rows.append((
                    ticker,
                    date.strftime("%Y-%m-%d"),
                    row.get("Open", None),
                    row.get("High", None),
                    row.get("Low", None),
                    row.get("Close", None),
                    int(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else 0,
                ))
            conn.executemany("INSERT OR REPLACE INTO daily_data VALUES (?,?,?,?,?,?,?)", rows)
            conn.commit()

    def delta_update(self, tickers: list[str]):
        conn = self._conn()
        chunks = [tickers[i:i+CHUNK_SIZE] for i in range(0, len(tickers), CHUNK_SIZE)]
        for idx, chunk in enumerate(chunks, 1):
            try:
                data = yf.download(
                    tickers=chunk,
                    period="5d",
                    interval="1d",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                    group_by="ticker"
                )
                self._store_chunk(conn, data)
            except Exception:
                pass
            time.sleep(SLEEP_BETWEEN_CHUNKS)
        conn.close()

    def get_scannable_universe(self) -> list[str]:
        sql = """
            SELECT ticker FROM (
                SELECT ticker, close, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                FROM daily_data
            )
            WHERE rn = 1 AND close > 10 AND volume > 300000
            ORDER BY ticker
        """
        with self._conn() as conn:
            rows = conn.execute(sql).fetchall()
        return [r[0] for r in rows]

    def get_ticker_data(self, ticker: str) -> pd.DataFrame:
        sql = "SELECT date, open, high, low, close, volume FROM daily_data WHERE ticker = ? ORDER BY date"
        with self._conn() as conn:
            df = pd.read_sql_query(sql, conn, params=(ticker,))
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df.astype({"close": float, "high": float, "low": float, "open": float, "volume": int})

    def get_all_data(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        result = {}
        placeholders = ",".join("?" for _ in tickers)
        sql = f"SELECT ticker, date, open, high, low, close, volume FROM daily_data WHERE ticker IN ({placeholders}) ORDER BY ticker, date"
        with self._conn() as conn:
            df = pd.read_sql_query(sql, conn, params=tickers)
        for ticker in tickers:
            tdf = df[df["ticker"] == ticker].copy()
            if tdf.empty:
                continue
            tdf["date"] = pd.to_datetime(tdf["date"])
            tdf.set_index("date", inplace=True)
            tdf.drop(columns=["ticker"], inplace=True)
            result[ticker] = tdf.astype({"close": float, "high": float, "low": float, "open": float, "volume": int})
        return result

    def get_stats(self) -> dict:
        with self._conn() as conn:
            ticker_count = conn.execute("SELECT COUNT(DISTINCT ticker) FROM daily_data").fetchone()[0]
            row_count = conn.execute("SELECT COUNT(*) FROM daily_data").fetchone()[0]
            last_date = conn.execute("SELECT MAX(date) FROM daily_data").fetchone()[0]
        return {"tickers": ticker_count, "rows": row_count, "last_date": last_date}

    def tickers_in_db(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT DISTINCT ticker FROM daily_data ORDER BY ticker").fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _log_failed(failed: list[str]):
        if not failed:
            return
        with open("failed_tickers.log", "a") as f:
            f.write(f"--- Bulk download failures ---\n")
            for t in failed:
                f.write(f"{t}\n")
