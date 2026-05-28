import argparse
import json
import logging
import os
import sys
import time

from src.universe import fetch_universe, fetch_universe_with_prices, filter_liquid, save_universe
from src.fetcher import SmartFetcher
from src.scanner import QullamaggieScanner
from src.alerts import TelegramAlerter
from src.utils import now_est, format_est

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
alert = TelegramAlerter()


def save_results(results: list[dict], prefix: str = "scan"):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    date_str = now_est().strftime("%Y%m%d")
    filename = f"{prefix}_{date_str}.json"
    path = os.path.join(RESULTS_DIR, filename)
    try:
        with open(path, "w") as f:
            json.dump({
                "timestamp": format_est(),
                "count": len(results),
                "results": results,
            }, f, indent=2)
        logger.info("Results saved to %s", path)
    except Exception as e:
        logger.warning("Failed to save results: %s", e)


TIER1_LIMIT = 1000


def _get_targets() -> list[str]:
    rows = fetch_universe_with_prices()
    targets = filter_liquid(rows)
    if not targets:
        logger.warning("No liquid stocks — falling back to all from universe")
        tickers = fetch_universe()
        targets = tickers
    save_universe(targets)
    return targets


def _tiered_fetch_scan(targets: list[str], prefix: str) -> list[dict]:
    tier1 = targets[:TIER1_LIMIT]
    tier2 = targets[TIER1_LIMIT:]

    data = {}
    if tier1:
        logger.info("Tier 1: %d stocks (1yr data, full scan)", len(tier1))
        f1 = SmartFetcher(chunk_size=25)
        data.update(f1.eod_fetch(tier1))
    if tier2:
        logger.info("Tier 2: %d stocks (6mo data, lite scan)", len(tier2))
        f2 = SmartFetcher(chunk_size=50)
        data.update(f2.semi_annual_fetch(tier2))

    if not data:
        return []

    scanner = QullamaggieScanner(data)
    return scanner.scan()


def cmd_scan():
    overall_start = time.perf_counter()
    alert.send_status("✅ Scanner started — EOD scan")

    targets = _get_targets()
    logger.info("Targets: %d stocks", len(targets))

    results = _tiered_fetch_scan(targets, "eod")

    save_results(results, "eod")
    alert.send_summary(results)
    if results:
        for r in results:
            alert.send_breakout(r)

    elapsed = time.perf_counter() - overall_start
    logger.info("Total time: %.1f seconds", elapsed)


def cmd_weekly():
    overall_start = time.perf_counter()
    alert.send_status("📋 Weekly deep scan starting")
    targets = _get_targets()
    logger.info("Targets: %d stocks", len(targets))

    results = _tiered_fetch_scan(targets, "weekly")

    save_results(results, "weekly")
    alert.send_summary(results)

    top = sorted(results, key=lambda r: r["volume_ratio"], reverse=True)[:20]
    if top:
        alert.send_watchlist(top)

    elapsed = time.perf_counter() - overall_start
    logger.info("Weekly scan total time: %.1f seconds", elapsed)


def cmd_check(ticker: str):
    alert.send_status(f"🔍 Checking {ticker.upper()}...")
    fetcher = SmartFetcher()
    df = fetcher.fetch_single(ticker.upper())
    if df is None:
        alert.send_status(f"❌ No data for {ticker.upper()}")
        return
    analysis = QullamaggieScanner.check_single(ticker.upper(), df)
    alert.send_check(ticker.upper(), analysis)


def cmd_status():
    alert.send_status(
        f"📊 **Scanner Status**\n"
        f"✅ Bot operational\n"
        f"⏰ {format_est()}\n"
        f"📁 Results stored in results/\n"
        f"📅 EOD scan: Mon-Fri 4:30 PM EST\n"
        f"📋 Weekly: Sun 8 PM EST"
    )


def main():
    parser = argparse.ArgumentParser(description="Qullamaggie Breakout Scanner")
    parser.add_argument("--scan", action="store_true", help="Full EOD scan")
    parser.add_argument("--weekly", action="store_true", help="Deep weekly scan")
    parser.add_argument("--check", type=str, metavar="TICKER", help="Check single stock")
    parser.add_argument("--status", action="store_true", help="Send status message")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(1)

    try:
        if args.scan:
            cmd_scan()
        elif args.weekly:
            cmd_weekly()
        elif args.check:
            cmd_check(args.check.upper())
        elif args.status:
            cmd_status()
    except Exception as e:
        logger.exception("Fatal error")
        alert.send_status(f"❌ Scanner error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
