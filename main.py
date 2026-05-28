import json
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

from universe import fetch_universe, save_universe, load_universe
from data_engine import StockDataEngine
from scanner import QullamaggieScanner
from alerts import (
    format_scan_results,
    send_telegram_alert,
    send_csv_export,
    send_sectors_report,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_USER_IDS = [
    int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()
]

DB_PATH = "stocks.db"
UNIVERSE_PATH = "universe.csv"
RESULTS_PATH = "last_results.json"
SECTOR_TICKERS = ["XLF", "XLK", "XLV", "XLI", "XLB", "XLE", "XLU", "XLY", "XLP", "XLC", "XLRE"]

engine = StockDataEngine(db_path=DB_PATH)
scheduler = AsyncIOScheduler(timezone="America/New_York")

_bot = None
last_results: list[dict] = []

def authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if user_id and user_id in ALLOWED_USER_IDS:
            return await func(update, context)
        await update.message.reply_text("⛔ Unauthorized. You are not on the allowed users list.")
    return wrapper

async def run_scan_and_notify(context: ContextTypes.DEFAULT_TYPE = None) -> list[dict]:
    global last_results
    tickers = engine.get_scannable_universe()
    if not tickers:
        logger.warning("No scannable tickers found in DB.")
        return []
    logger.info("Scanning %d tickers...", len(tickers))
    data = engine.get_all_data(tickers)
    scanner = QullamaggieScanner(data)
    results = scanner.scan()
    last_results = results
    _save_results(results)
    return results

async def run_sector_scan() -> dict:
    tickers = SECTOR_TICKERS
    data = engine.get_all_data(tickers)
    results = QullamaggieScanner.analyze_sectors(data)
    return results

async def full_setup(context: ContextTypes.DEFAULT_TYPE = None, chat_id: int | None = None):
    progress_chat = chat_id
    bot = context.bot if context else None

    if progress_chat and bot:
        await bot.send_message(chat_id=progress_chat, text="📡 Downloading stock universe from NASDAQ...")
    try:
        tickers = fetch_universe()
        save_universe(tickers, UNIVERSE_PATH)
        logger.info("Universe: %d tickers saved", len(tickers))
    except Exception as e:
        logger.warning("Remote universe fetch failed: %s", e)
        existing = load_universe(UNIVERSE_PATH) if os.path.exists(UNIVERSE_PATH) else []
        if existing:
            tickers = existing
            logger.info("Falling back to cached universe.csv (%d tickers)", len(tickers))
            if progress_chat and bot:
                await bot.send_message(chat_id=progress_chat, text=f"⚠️ NASDAQ unreachable. Using cached universe.csv ({len(tickers)} tickers). Run /setup again later to refresh.")
        else:
            msg = f"❌ Failed to fetch universe and no cached file found: {e}"
            logger.error(msg)
            if progress_chat and bot:
                await bot.send_message(chat_id=progress_chat, text=msg)
            return

    if progress_chat and bot:
        await bot.send_message(chat_id=progress_chat, text=f"📥 Downloading 1-year data for {len(tickers)} stocks + sectors... This takes ~10-15 min.")
    failed = engine.bulk_download(tickers + SECTOR_TICKERS)
    msg = f"✅ Setup complete! {len(tickers)} tickers in universe."
    if failed:
        msg += f"\n⚠️ {len(failed)} tickers failed (logged to failed_tickers.log)"
    logger.info("Setup complete. %d tickers, %d failed", len(tickers), len(failed))
    if progress_chat and bot:
        await bot.send_message(chat_id=progress_chat, text=msg)

async def scheduled_full_update():
    logger.info("Scheduled: Weekly full update starting...")
    tickers = load_universe(UNIVERSE_PATH)
    if not tickers:
        logger.warning("No universe file found, skipping scheduled update")
        return
    engine.bulk_download(tickers + SECTOR_TICKERS)
    logger.info("Scheduled: Weekly full update complete")

async def scheduled_daily_scan():
    global _bot
    logger.info("Scheduled: Daily delta update + scan starting...")
    tickers = load_universe(UNIVERSE_PATH)
    if not tickers:
        logger.warning("No universe file found, skipping scheduled scan")
        return
    engine.delta_update(tickers + SECTOR_TICKERS)
    results = await run_scan_and_notify()
    if not _bot and BOT_TOKEN:
        from telegram import Bot as TelegramBot
        _bot = TelegramBot(token=BOT_TOKEN)
    if not _bot:
        return
    if results:
        for uid in ALLOWED_USER_IDS:
            try:
                await send_telegram_alert(_bot, uid, results)
            except Exception as e:
                logger.error("Failed to send alert to %d: %s", uid, e)
    else:
        for uid in ALLOWED_USER_IDS:
            try:
                await _bot.send_message(chat_id=uid, text="📭 Daily scan complete — No breakouts found.")
            except Exception as e:
                logger.error("Failed to send alert to %d: %s", uid, e)

def _save_results(results: list[dict]):
    try:
        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass

def _load_results() -> list[dict]:
    try:
        with open(RESULTS_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# --- Telegram Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Welcome to Qullamaggie Breakout Scanner Bot!\n\n"
        "Type /help to see all commands.\n\n"
        "Quick start: Type /setup to download stock data first."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **Commands**\n\n"
        "🔹 /start — Welcome message\n"
        "🔹 /help — Show this help\n"
        "🔹 /setup — First-time: download universe + 1yr data\n"
        "🔹 /scan — Run breakout scanner on existing data\n"
        "🔹 /update — Delta update (last 5 days) + scan\n"
        "🔹 /full_update — Full 1-year re-download + scan\n"
        "🔹 /sectors — Show sector performance\n"
        "🔹 /status — Database stats\n"
        "🔹 /export — Last scan results as CSV file\n"
        "🔹 /users — Show authorized user IDs\n\n"
        "**Auto-schedule:**\n"
        "📅 Sunday 8PM EST — Full data refresh\n"
        "📅 Mon–Fri 4:30PM EST — Delta update + auto-scan → results sent here"
    )

@authorized
async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else None
    await update.message.reply_text("🔄 Starting setup... This takes 10-15 minutes. I'll notify you when done.")
    await full_setup(context, chat_id)

@authorized
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Scanning...")
    try:
        results = await run_scan_and_notify()
        msg = format_scan_results(results)
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Scan failed: {e}")
        logger.exception("Scan error")

@authorized
async def update_command(upd: Update, context: ContextTypes.DEFAULT_TYPE):
    await upd.message.reply_text("📥 Delta updating last 5 days...")
    try:
        tickers = load_universe(UNIVERSE_PATH)
        if not tickers:
            await upd.message.reply_text("❌ No universe file found. Run /setup first.")
            return
        engine.delta_update(tickers + SECTOR_TICKERS)
        await upd.message.reply_text("✅ Delta update complete. Now scanning...")
        results = await run_scan_and_notify()
        msg = format_scan_results(results)
        await upd.message.reply_text(msg)
    except Exception as e:
        await upd.message.reply_text(f"❌ Update + scan failed: {e}")
        logger.exception("Update error")

@authorized
async def full_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Full re-download + scan starting... This takes 10-15 min.")
    try:
        tickers = load_universe(UNIVERSE_PATH)
        if not tickers:
            await update.message.reply_text("❌ No universe file found. Run /setup first.")
            return
        engine.bulk_download(tickers + SECTOR_TICKERS)
        await update.message.reply_text("✅ Full download complete. Now scanning...")
        results = await run_scan_and_notify()
        msg = format_scan_results(results)
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Full update failed: {e}")
        logger.exception("Full update error")

@authorized
async def sectors(upd: Update, context: ContextTypes.DEFAULT_TYPE):
    await upd.message.reply_text("📊 Analyzing sectors...")
    try:
        results = await run_sector_scan()
        await send_sectors_report(context.bot, upd.effective_chat.id, results)
    except Exception as e:
        await upd.message.reply_text(f"❌ Sector analysis failed: {e}")
        logger.exception("Sectors error")

@authorized
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stats = engine.get_stats()
        msg = (
            f"📊 **Database Status**\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📌 Tickers    : {stats['tickers']}\n"
            f"📊 Data rows  : {stats['rows']:,}\n"
            f"📅 Last date  : {stats['last_date'] or 'N/A'}\n"
            f"📁 DB path    : {DB_PATH}\n"
            f"👤 Auth users : {len(ALLOWED_USER_IDS)}\n"
        )
        if last_results:
            msg += f"🔍 Last scan   : {len(last_results)} breakouts"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Status error: {e}")

@authorized
async def export(upd: Update, context: ContextTypes.DEFAULT_TYPE):
    results = last_results or _load_results()
    if not results:
        await upd.message.reply_text("📭 No scan results to export. Run /scan first.")
        return
    try:
        await send_csv_export(context.bot, upd.effective_chat.id, results)
    except Exception as e:
        await upd.message.reply_text(f"❌ Export failed: {e}")

@authorized
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["👤 **Authorized Users**\n"]
    for uid in ALLOWED_USER_IDS:
        lines.append(f"• `{uid}`")
    if not ALLOWED_USER_IDS:
        lines.append("(none configured)")
    await update.message.reply_text("\n".join(lines))

async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else "unknown"
    await update.message.reply_text(f"🆔 Your Telegram User ID: `{user_id}`")

# --- Setup ---

def setup_scheduler():
    scheduler.add_job(
        scheduled_full_update,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone="America/New_York"),
        id="weekly_full_update",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_daily_scan,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone="America/New_York"),
        id="daily_delta_scan",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started: Sunday 8PM full update, Mon-Fri 4:30PM delta+scan")

def build_app() -> Application:
    async def post_init(app: Application):
        await set_commands(app)
        setup_scheduler()
        logger.info("Bot started. Scheduler running.")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("update", update_command))
    app.add_handler(CommandHandler("full_update", full_update))
    app.add_handler(CommandHandler("sectors", sectors))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("myid", my_id))

    return app

async def set_commands(app: Application):
    commands = [
        BotCommand("start", "Welcome"),
        BotCommand("help", "Show all commands"),
        BotCommand("setup", "First-time: download universe + 1yr data"),
        BotCommand("scan", "Run breakout scanner"),
        BotCommand("update", "Delta update + scan"),
        BotCommand("full_update", "Full re-download + scan"),
        BotCommand("sectors", "Show sector performance"),
        BotCommand("status", "Database stats"),
        BotCommand("export", "Last results as CSV"),
        BotCommand("users", "Show authorized users"),
    ]
    try:
        await app.bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("Could not set bot commands: %s", e)

def main():
    global last_results
    last_results = _load_results()

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Create a .env file with BOT_TOKEN=...")
        return

    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
