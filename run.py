#!/usr/bin/env python3
"""kalsim Risk Desk — TUI entry point.

Fetches positions via REST at startup, connects websocket for live updates,
and launches an interactive terminal UI for portfolio risk management.
"""
import asyncio
import logging
import os
import sys
import signal
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    filename="kalsim.log",
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def check_credentials():
    if not os.environ.get("KALSHI_KEY_ID") or not os.environ.get("KALSHI_PRIVATE_KEY"):
        print("No Kalshi credentials found.")
        print("Set KALSHI_KEY_ID and KALSHI_PRIVATE_KEY in .env or environment.")
        sys.exit(1)


def fetch_initial_state():
    """Fetch positions and orderbooks via REST (one-time startup cost)."""
    from src.position_feed import PositionFeed
    from src.book_state import BookState

    feed = PositionFeed()
    positions = feed.get_positions()

    state = BookState()

    try:
        cash, portfolio_val = feed.client.get_balance()
        state.cash_balance = cash
        state.portfolio_value = portfolio_val
    except Exception:
        pass

    state.set_positions(positions)

    # Populate initial orderbooks from REST
    for pos in positions:
        try:
            ob = feed.client.get_orderbook(pos.contract_id)
            yes_levels = ob.get("yes", [])
            no_levels = ob.get("no", [])
            state.apply_orderbook_snapshot(pos.contract_id, yes_levels, no_levels)
        except Exception:
            pass

    # Store market metadata for reference
    for pos in positions:
        try:
            market = feed.client.get_market(pos.contract_id)
            state.market_meta[pos.contract_id] = market
        except Exception:
            pass

    return state, feed.config.kalshi


def run_tui():
    check_credentials()

    print("Fetching positions and orderbooks...")
    book_state, kalshi_config = fetch_initial_state()

    n = len(book_state.positions)
    print(f"Loaded {n} position{'s' if n != 1 else ''}. Launching TUI...")

    from src.tui.app import RiskDeskApp
    from src.ws_client import KalshiWS
    from src.nav_store import NavStore

    nav_store = NavStore()
    app = RiskDeskApp(book_state, nav_store=nav_store)
    ws_client = KalshiWS(kalshi_config, book_state)

    async def run_with_ws():
        await ws_client.start()
        try:
            await app.run_async()
        finally:
            await ws_client.stop()
            nav_store.close()

    try:
        asyncio.run(run_with_ws())
    except KeyboardInterrupt:
        nav_store.close()


def run_desktop():
    import subprocess
    import shutil

    npm = shutil.which("npm")
    if npm is None:
        print("npm not found. Install Node.js to use desktop mode.")
        sys.exit(1)

    desktop_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop")
    if not os.path.exists(os.path.join(desktop_dir, "node_modules")):
        print("Installing desktop dependencies...")
        subprocess.run([npm, "install"], cwd=desktop_dir, check=True)

    print("Starting desktop app...")
    subprocess.run([npm, "run", "dev"], cwd=desktop_dir)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="kalsim Risk Desk")
    parser.add_argument("--mode", choices=["tui", "desktop"], default="desktop")
    args = parser.parse_args()

    if args.mode == "tui":
        run_tui()
    else:
        run_desktop()


if __name__ == "__main__":
    main()
