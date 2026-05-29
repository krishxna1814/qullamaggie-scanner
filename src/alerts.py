import logging
import os

import requests

from src.utils import format_est

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")


def _chart_url(ticker: str) -> str:
    return f"https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=d&s=l"


def _fmt_vol(vol: int) -> str:
    if vol >= 1_000_000_000:
        return f"{vol/1_000_000_000:.1f}B"
    if vol >= 1_000_000:
        return f"{vol/1_000_000:.1f}M"
    if vol >= 1_000:
        return f"{vol/1_000:.1f}K"
    return str(vol)


class TelegramAlerter:
    def __init__(self, token: str = TELEGRAM_TOKEN, chat_id: str = CHAT_ID):
        self.token = token
        self.chat_ids = [c.strip() for c in chat_id.split(",") if c.strip()] if chat_id else []
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.enabled = bool(token and self.chat_ids)

    def _send(self, text: str) -> bool:
        if not self.enabled:
            logger.info("Telegram disabled (set TELEGRAM_TOKEN and CHAT_ID env vars)")
            return False
        all_ok = True
        for cid in self.chat_ids:
            try:
                resp = requests.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": cid, "text": text, "parse_mode": "Markdown"},
                    timeout=15,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.warning("Telegram send to %s failed: %s", cid, e)
                all_ok = False
        return all_ok

    def _send_chart(self, ticker: str, caption: str) -> bool:
        if not self.enabled:
            return False
        chart_url = _chart_url(ticker)
        all_ok = True
        for cid in self.chat_ids:
            try:
                resp = requests.post(
                    f"{self.base_url}/sendPhoto",
                    json={
                        "chat_id": cid,
                        "photo": chart_url,
                        "caption": caption,
                        "parse_mode": "Markdown",
                    },
                    timeout=20,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.warning("Telegram sendPhoto to %s failed: %s", cid, e)
                all_ok = False
        return all_ok

    def send_breakout(self, result: dict) -> bool:
        ticker = result["ticker"]
        period = result.get("period", "")
        period_tag = f" [{period}]" if period else ""
        caption = (
            f"#{result['rank']} {ticker}{period_tag}\n"
            f"💵 ${result['price']} | 📈 +{result['total_return']}%\n"
            f"📊 ADR: {result['adr']}% | RSI: {result['rsi']}\n"
            f"📊 Vol: {_fmt_vol(result['avg_volume'])}"
        )
        if self._send_chart(ticker, caption):
            return True
        msg = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 #{result['rank']} {ticker}{period_tag}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price      : ${result['price']}\n"
            f"📊 Return     : {result['total_return']}%\n"
            f"📈 ADR        : {result['adr']}%\n"
            f"📊 Avg Vol    : {result['avg_volume']:,}\n"
            f"📊 RSI        : {result['rsi']}\n"
            f"📈 [Chart]({_chart_url(ticker)})\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        return self._send(msg)

    def send_summary(self, results: list[dict], period: str = "") -> bool:
        if not results:
            return self._send(f"📭 No stocks passed filters{period}.")
        label = f" [{period}]" if period else ""
        lines = [f"🎯 **TOP GAINERS{label}** — {len(results)} stocks\n"]
        for r in results:
            lines.append(
                f"#{r['rank']:2} {r['ticker']:5} 📈+{r['total_return']}%  "
                f"ADR {r['adr']}%  Vol {_fmt_vol(r['avg_volume'])}"
            )
        msg = "\n".join(lines)
        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            ok = True
            for p in parts:
                ok = self._send(p) and ok
            return ok
        return self._send(msg)

    def send_status(self, message: str) -> bool:
        return self._send(message)

    def send_check(self, ticker: str, analysis: str) -> bool:
        msg = f"🔍 **{ticker} Check**\n{analysis}\n[📈 Chart]({_chart_url(ticker)})"
        return self._send(msg)
