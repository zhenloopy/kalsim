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


def main():
    check_credentials()

    print("Fetching positions and orderbooks...")
    book_state, kalshi_config = fetch_initial_state()

    n = len(book_state.positions)
    print(f"Loaded {n} position{'s' if n != 1 else ''}. Launching TUI...")

    from src.tui.app import RiskDeskApp
    from src.ws_client import KalshiWS

    app = RiskDeskApp(book_state)
    ws_client = KalshiWS(kalshi_config, book_state)

    async def run_with_ws():
        await ws_client.start()
        try:
            await app.run_async()
        finally:
            await ws_client.stop()

    try:
        asyncio.run(run_with_ws())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
