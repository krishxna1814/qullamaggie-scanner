import json
import logging
import os
import re

import requests
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
CHAT_ID = os.environ.get("CHAT_ID", "")


def trigger_workflow(workflow: str, inputs: dict = None):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {"error": "GITHUB_TOKEN or GITHUB_REPO not set"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    body = {"ref": "main"}
    if inputs:
        body["inputs"] = inputs
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        if resp.status_code in (204, 201, 200):
            return {"ok": True}
        return {"error": f"GitHub API: {resp.status_code} {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def fetch_latest_results() -> dict:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/results"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return {}
        files = resp.json()
        json_files = [f for f in files if f["name"].endswith(".json")]
        if not json_files:
            return {}
        latest = max(json_files, key=lambda f: f["name"])
        dl = requests.get(latest["download_url"], timeout=15)
        return dl.json() if dl.status_code == 200 else {}
    except Exception:
        return {}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Qullamaggie Breakout Scanner Bot**\n\n"
        "Type /help to see all commands.\n\n"
        "Quick start:\n"
        "1. Bot automatically scans on schedule\n"
        "2. Use /scan to trigger immediately\n"
        "3. Results sent here automatically"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Commands**\n\n"
        "🔹 /scan — Trigger full EOD scan\n"
        "🔹 /quick — Trigger quick intraday scan\n"
        "🔹 /weekly — Trigger deep weekly scan\n"
        "🔹 /check SYMBOL — Analyze single stock\n"
        "🔹 /status — Bot + last scan status\n"
        "🔹 /last — Show last scan results\n"
        "🔹 /help — This message\n\n"
        "**Schedules (auto):**\n"
        "📅 Mon-Fri 4:30 PM EST — EOD scan\n"
        "📅 Mon-Fri 12:30 PM EST — Midday scan\n"
        "📅 Mon-Fri every 30min — Intraday scan\n"
        "📅 Sunday 8 PM EST — Weekly deep scan"
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Starting full EOD scan... 3-5 minutes.")
    result = trigger_workflow("scanner.yml", {"mode": "scan"})
    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")


async def cmd_quick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Quick scan starting...")
    result = trigger_workflow("scanner.yml", {"mode": "quick"})
    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")


async def cmd_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Weekly deep scan starting... takes 5-10 min.")
    result = trigger_workflow("scanner.yml", {"mode": "weekly"})
    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /check SYMBOL\nExample: /check AAPL")
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"🔍 Checking {ticker}...")
    result = trigger_workflow("scanner.yml", {"mode": f"check_{ticker}"})
    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
    await update.message.reply_text(f"⏳ Check submitted. Check Telegram for analysis of {ticker}.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **Bot Status**\n"
        f"✅ Bot running\n"
        f"📡 GitHub: {GITHUB_REPO or 'not set'}\n"
        f"📅 Scanner auto-scheduled via Actions\n"
        f"💡 Use /help for commands"
    )


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = fetch_latest_results()
    if not data:
        await update.message.reply_text("📭 No results found yet. Run /scan first.")
        return
    results = data.get("results", [])
    timestamp = data.get("timestamp", "unknown")
    msg = f"📊 **Last Scan** ({timestamp})\n"
    msg += f"Found {len(results)} breakouts\n\n"
    for r in results[:5]:
        ep = " 🔥" if r.get("ep_candidate") else ""
        msg += f"{r['ticker']:5} ${r['price']:<7.2f} {r['volume_ratio']:>4.2f}x{ep}\n"
    if len(results) > 5:
        msg += f"\n... and {len(results) - 5} more. Use /export to get CSV."
    await update.message.reply_text(msg)


def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("quick", cmd_quick))
    app.add_handler(CommandHandler("weekly", cmd_weekly))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("last", cmd_last))

    logger.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
