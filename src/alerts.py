import json
import logging
import os

import requests

from src.utils import format_est

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")


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
        msg = (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 BREAKOUT ALERT{' 🔥 EP' if result.get('ep_candidate') else ''}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Ticker   : {result['ticker']}\n"
            f"💰 Price    : ${result['price']}\n"
            f"📊 Volume   : {result['volume_ratio']}x avg\n"
            f"📈 52W High : {result['distance_from_52w_high']}%\n"
            f"🎯 Tight    : {result['consolidation_tightness']}%\n"
            f"⚡ Signal   : {result['signal_strength']}\n"
            f"⏰ Time     : {result.get('scan_time', format_est())}\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        return self._send(msg)

    def send_summary(self, results: list[dict]) -> bool:
        if not results:
            return self._send("📭 No breakouts found today.")
        sorted_r = sorted(results, key=lambda r: r["volume_ratio"], reverse=True)
        count = len(sorted_r)
        strong = sum(1 for r in sorted_r if r.get("ep_candidate"))
        msg = (
            f"🎯 **SCAN COMPLETE**\n"
            f"📊 Found {count} breakouts"
        )
        if strong:
            msg += f"\n🔥 {strong} EP candidates"
        msg += f"\n⏰ {format_est()}"
        return self._send(msg)

    def send_status(self, message: str) -> bool:
        return self._send(message)

    def send_watchlist(self, results: list[dict]) -> bool:
        if not results:
            return self._send("📭 Weekly scan complete — No breakouts found.")
        sorted_r = sorted(results, key=lambda r: r["volume_ratio"], reverse=True)
        lines = ["📋 **WEEKLY WATCHLIST**\n"]
        for r in sorted_r:
            ep = " 🔥" if r.get("ep_candidate") else ""
            lines.append(
                f"{r['ticker']:5} | ${r['price']:>7.2f} | "
                f"{r['volume_ratio']:>4.2f}x | {r['distance_from_52w_high']:>5.2f}%{ep}"
            )
        msg = "\n".join(lines)
        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            ok = True
            for p in parts:
                ok = self._send(p) and ok
            return ok
        return self._send(msg)

    def send_check(self, ticker: str, analysis: str) -> bool:
        msg = f"🔍 **{ticker} Check**\n{analysis}"
        return self._send(msg)
