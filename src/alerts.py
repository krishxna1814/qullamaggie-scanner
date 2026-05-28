import logging
import os

import requests

from src.utils import format_est

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")


def _chart_url(ticker: str) -> str:
    return f"https://finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=d&s=l"


class TelegramAlerter:
    def __init__(self, token: str = TELEGRAM_TOKEN, chat_id: str = CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.enabled = bool(token and chat_id)

    def _send(self, text: str) -> bool:
        if not self.enabled:
            logger.info("Telegram disabled (set TELEGRAM_TOKEN and CHAT_ID env vars)")
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)
            return False

    def send_breakout(self, result: dict) -> bool:
        ticker = result["ticker"]
        msg = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 #{result['rank']} {ticker}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Price      : ${result['price']}\n"
            f"📊 Return     : {result['total_return']}%\n"
            f"📈 ADR        : {result['adr']}%\n"
            f"📊 avg Vol    : {result['avg_volume']:,}\n"
            f"📈 [Chart]({_chart_url(ticker)})\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        return self._send(msg)

    def send_summary(self, results: list[dict], period: str = "") -> bool:
        if not results:
            return self._send(f"📭 No stocks passed filters{period}.")
        label = f" ({period})" if period else ""
        lines = [f"🎯 **TOP GAINERS{label}**\n"]
        for r in results:
            lines.append(
                f"#{r['rank']} {r['ticker']:5} | +{r['total_return']}% | "
                f"ADR {r['adr']}% | Vol {r['avg_volume']:,}\n"
                f"[📈 Chart]({_chart_url(r['ticker'])})\n"
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
