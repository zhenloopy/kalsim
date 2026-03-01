import asyncio
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from src.schema import Position
from src.position_feed import compute_mid_from_orderbook, fee_adjusted_breakeven

logger = logging.getLogger(__name__)


@dataclass
class TickerData:
    last_price: float = 0.0
    volume: int = 0
    open_interest: int = 0
    yes_bid: float = 0.0
    yes_ask: float = 0.0


class BookState:
    """Single source of truth for all live market data.

    Updated by websocket callbacks, read by TUI and risk computations.
    All operations are synchronous since Textual runs a single asyncio loop.
    """

    def __init__(self):
        self.positions: list[Position] = []
        self.orderbooks: dict[str, dict] = {}
        self.ticker_data: dict[str, TickerData] = {}
        self.market_meta: dict[str, dict] = {}
        self.cash_balance: float = 0.0
        self.portfolio_value: float = 0.0
        self._ws_connected = False
        self._last_update: datetime | None = None
        self._callbacks: list = []

    @property
    def bankroll(self) -> float:
        return self.cash_balance + self.portfolio_value

    @property
    def ws_connected(self):
        return self._ws_connected

    @ws_connected.setter
    def ws_connected(self, val):
        self._ws_connected = val
        self._notify()

    @property
    def last_update(self):
        return self._last_update

    def on_change(self, callback):
        self._callbacks.append(callback)

    def _notify(self):
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def set_positions(self, positions: list[Position]):
        self.positions = positions
        self._last_update = datetime.now(timezone.utc)
        self._notify()

    def get_tickers(self) -> list[str]:
        return [p.contract_id for p in self.positions]

    def apply_orderbook_snapshot(self, ticker: str, yes_levels: list, no_levels: list):
        """Apply a full orderbook snapshot. Levels: [[price_cents, qty], ...]"""
        book = {"yes": {}, "no": {}}
        for price, qty in yes_levels:
            if qty > 0:
                book["yes"][price] = qty
        for price, qty in no_levels:
            if qty > 0:
                book["no"][price] = qty
        self.orderbooks[ticker] = book
        self._update_position_mid(ticker)
        self._last_update = datetime.now(timezone.utc)
        self._notify()

    def apply_orderbook_delta(self, ticker: str, price: int, delta: int, side: str):
        """Apply incremental orderbook update."""
        if ticker not in self.orderbooks:
            self.orderbooks[ticker] = {"yes": {}, "no": {}}
        book = self.orderbooks[ticker]
        current = book[side].get(price, 0)
        new_qty = current + delta
        if new_qty <= 0:
            book[side].pop(price, None)
        else:
            book[side][price] = new_qty
        self._update_position_mid(ticker)
        self._last_update = datetime.now(timezone.utc)
        self._notify()

    def apply_ticker_update(self, ticker: str, data: dict):
        if ticker not in self.ticker_data:
            self.ticker_data[ticker] = TickerData()
        td = self.ticker_data[ticker]
        if "yes_price" in data:
            td.last_price = data["yes_price"] / 100.0 if data["yes_price"] > 1 else data["yes_price"]
        if "volume" in data:
            td.volume = data["volume"]
        if "open_interest" in data:
            td.open_interest = data["open_interest"]
        if "yes_bid" in data:
            td.yes_bid = data["yes_bid"] / 100.0 if data["yes_bid"] > 1 else data["yes_bid"]
        if "yes_ask" in data:
            td.yes_ask = data["yes_ask"] / 100.0 if data["yes_ask"] > 1 else data["yes_ask"]
        self._last_update = datetime.now(timezone.utc)
        self._notify()

    def apply_fill(self, ticker: str, side: str, count: int, price_cents: int) -> str | None:
        """Update position from a fill message.

        Returns the ticker if a new position was created, None otherwise.
        """
        for pos in self.positions:
            if pos.contract_id == ticker:
                if side == "yes":
                    pos.quantity += count
                else:
                    pos.quantity -= count
                self._last_update = datetime.now(timezone.utc)
                self._notify()
                return None

        entry = price_cents / 100.0 if price_cents > 1 else price_cents
        quantity = count if side == "yes" else -count
        if side == "no":
            entry = 1.0 - entry
        mid = entry
        placeholder_resolve = datetime.now(timezone.utc) + timedelta(days=365)

        pos = Position(
            contract_id=ticker,
            platform="kalshi",
            canonical_event_id=ticker,
            quantity=quantity,
            entry_price=entry,
            current_mid=mid,
            market_prob=mid,
            model_prob=mid,
            edge=0.0,
            resolves_at=placeholder_resolve,
            tte_days=365.0,
            fee_adjusted_breakeven=fee_adjusted_breakeven(mid, 0.07, quantity > 0),
        )
        self.positions.append(pos)
        logger.info(f"New position created from fill: {ticker} qty={quantity} entry={entry}")
        self._last_update = datetime.now(timezone.utc)
        self._notify()
        return ticker

    def update_position_metadata(self, ticker: str, market: dict, orderbook: dict):
        """Fill in full market metadata for a position created from a fill."""
        for pos in self.positions:
            if pos.contract_id == ticker:
                close_time = market.get("close_time", market.get("expiration_time", ""))
                if close_time:
                    resolves_at = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                    pos.resolves_at = resolves_at
                    pos.tte_days = max((resolves_at - datetime.now(timezone.utc)).total_seconds() / 86400.0, 0.0)

                pos.canonical_event_id = market.get("event_ticker", market.get("series_ticker", ticker))
                pos.title = market.get("title", "")
                self.market_meta[ticker] = market

                yes_levels = orderbook.get("yes", [])
                no_levels = orderbook.get("no", [])
                self.apply_orderbook_snapshot(ticker, yes_levels, no_levels)
                break

    def _update_position_mid(self, ticker: str):
        """Recompute mid price for a position from its orderbook."""
        ob = self.get_orderbook_for_api(ticker)
        if ob is None:
            return
        mid = compute_mid_from_orderbook(ob)
        if mid is None:
            return
        for pos in self.positions:
            if pos.contract_id == ticker:
                pos.current_mid = mid
                pos.market_prob = mid
                pos.edge = pos.model_prob - mid
                break

    def get_orderbook_for_api(self, ticker: str) -> dict | None:
        """Convert internal orderbook format to the API-compatible format
        that liquidity.py and position_feed.py expect: {"yes": [[price, qty], ...], "no": [...]}
        Sorted descending by price (best first)."""
        if ticker not in self.orderbooks:
            return None
        book = self.orderbooks[ticker]
        yes_levels = sorted(book["yes"].items(), key=lambda x: -x[0])
        no_levels = sorted(book["no"].items(), key=lambda x: -x[0])
        return {
            "yes": [[p, q] for p, q in yes_levels],
            "no": [[p, q] for p, q in no_levels],
        }

    def get_mid(self, ticker: str) -> float | None:
        ob = self.get_orderbook_for_api(ticker)
        if ob is None:
            return None
        return compute_mid_from_orderbook(ob)

    def compute_nav(self) -> float:
        nav = self.cash_balance
        for pos in self.positions:
            nav += pos.market_value
        return nav

    def get_total_pnl(self) -> float:
        total = 0.0
        for pos in self.positions:
            total += pos.quantity * (pos.current_mid - pos.entry_price)
        return total

    def get_position_pnl(self, pos: Position) -> float:
        return pos.quantity * (pos.current_mid - pos.entry_price)
