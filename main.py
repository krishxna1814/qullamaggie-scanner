import argparse
import json
import logging
import os
import sys
import time

from src.universe import fetch_universe, fetch_universe_with_prices, filter_liquid, save_universe
from src.fetcher import SmartFetcher
from src.scanner import Scanner
from src.alerts import TelegramAlerter
from src.utils import now_est, format_est

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
alert = TelegramAlerter()

SCAN_CONFIGS = {
    "1mo": {"period": "1mo", "top_pct": 3.0},
    "3mo": {"period": "3mo", "top_pct": 3.0},
    "6mo": {"period": "6mo", "top_pct": 3.0},
}


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


def _get_targets() -> list[str]:
    rows = fetch_universe_with_prices()
    targets = filter_liquid(rows)
    if not targets:
        logger.warning("No stocks passed filters — falling back to all from universe")
        tickers = fetch_universe()
        targets = tickers
    save_universe(targets)
    return targets


def cmd_scan(label: str):
    config = SCAN_CONFIGS[label]
    overall_start = time.perf_counter()
    alert.send_status(f"✅ Scanner started — {label} scan")

    targets = _get_targets()
    logger.info("Targets: %d stocks", len(targets))

    fetcher = SmartFetcher(chunk_size=50)
    data = fetcher.fetch_by_period(targets, config["period"])
    if not data:
        alert.send_status("❌ No data fetched.")
        return

    scanner = Scanner(data)
    results = scanner.scan(top_pct=config["top_pct"])

    save_results(results, label)
    alert.send_summary(results, config["period"])
    if results:
        for r in results:
            alert.send_breakout(r)

    elapsed = time.perf_counter() - overall_start
    logger.info("Total time: %.1f seconds", elapsed)


def cmd_check(ticker: str):
    alert.send_status(f"🔍 Checking {ticker.upper()}...")
    fetcher = SmartFetcher()
    df = fetcher.fetch_single(ticker.upper())
    if df is None:
        alert.send_status(f"❌ No data for {ticker.upper()}")
        return
    analysis = Scanner.check_single(ticker.upper(), df)
    alert.send_check(ticker.upper(), analysis)


def cmd_status():
    alert.send_status(
        f"📊 **Scanner Status**\n"
        f"✅ Bot operational\n"
        f"⏰ {format_est()}\n"
        f"📁 Results stored in results/"
    )


def main():
    parser = argparse.ArgumentParser(description="Stock Top Gainers Scanner")
    parser.add_argument("--scan-1mo", action="store_true", help="Top gainers (1 month)")
    parser.add_argument("--scan-3mo", action="store_true", help="Top gainers (3 months)")
    parser.add_argument("--scan-6mo", action="store_true", help="Top gainers (6 months)")
    parser.add_argument("--check", type=str, metavar="TICKER", help="Check single stock")
    parser.add_argument("--status", action="store_true", help="Send status message")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(1)

    try:
        if args.scan_1mo:
            cmd_scan("1mo")
        elif args.scan_3mo:
            cmd_scan("3mo")
        elif args.scan_6mo:
            cmd_scan("6mo")
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
