import csv
import io
import logging
from datetime import datetime, timezone, timedelta

from telegram import Bot

logger = logging.getLogger(__name__)

EST = timezone(timedelta(hours=-5))

def format_scan_results(results: list[dict]) -> str:
    if not results:
        return "📭 No breakouts found in this scan."

    sorted_results = sorted(results, key=lambda r: r["volume_ratio"], reverse=True)
    now = datetime.now(EST).strftime("%I:%M %p EST")
    msg = f"🎯 SCAN COMPLETE — Found {len(sorted_results)} breakouts\n⏰ {now}\n\n"
    for r in sorted_results:
        ep = " 🔥 EP" if r["ep_candidate"] else ""
        strength = "⚡ " + r["signal_strength"]
        msg += (
            f"━━━━━━━━━━━━━━━━━\n"
            f"🚀 BREAKOUT ALERT{ep}\n"
            f"📌 Ticker     : {r['ticker']}\n"
            f"💰 Price      : ${r['price']}\n"
            f"📊 Vol Ratio  : {r['volume_ratio']}x average\n"
            f"📈 From High  : {r['distance_from_52w_high']}%\n"
            f"🎯 Tightness  : {r['consolidation_tightness']}%\n"
            f"{strength}\n"
        )
    return msg

def format_sectors(sector_results: dict) -> str:
    if not sector_results:
        return "📊 No sector data available."

    now = datetime.now(EST).strftime("%I:%M %p EST")
    msg = f"📊 SECTOR ROTATION — {now}\n━━━━━━━━━━━━━━━━━\n"
    for ticker in sorted(sector_results.keys()):
        s = sector_results[ticker]
        icon = "🟢" if s["uptrend"] else "🔴"
        trend = "UP" if s["uptrend"] else "DOWN"
        msg += f"{icon} {ticker:<4} ({s['name']:<16}) → {trend:<4} — {s['near_52w_high']} of high\n"
    return msg

def results_to_csv(results: list[dict]) -> str:
    if not results:
        return "ticker,price,volume_ratio,distance_from_52w_high,consolidation_tightness,ep_candidate,signal_strength"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "ticker", "price", "volume_ratio", "distance_from_52w_high",
        "consolidation_tightness", "ep_candidate", "signal_strength"
    ])
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    return output.getvalue()

async def send_telegram_alert(bot: Bot, chat_id: int, results: list[dict]):
    msg = format_scan_results(results)
    if len(msg) > 4000:
        parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
        for part in parts:
            await bot.send_message(chat_id=chat_id, text=part)
    else:
        await bot.send_message(chat_id=chat_id, text=msg)

async def send_csv_export(bot: Bot, chat_id: int, results: list[dict]):
    csv_content = results_to_csv(results)
    await bot.send_document(
        chat_id=chat_id,
        document=io.BytesIO(csv_content.encode()),
        filename="scan_results.csv"
    )

async def send_sectors_report(bot: Bot, chat_id: int, sector_results: dict):
    msg = format_sectors(sector_results)
    await bot.send_message(chat_id=chat_id, text=msg)
