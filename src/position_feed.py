from datetime import datetime, timezone
from src.schema import Position
from src.kalshi_client import KalshiClient
from src.config import FeedConfig


def compute_mid_from_orderbook(orderbook):
    yes_bids = orderbook.get("yes", [])
    no_bids = orderbook.get("no", [])

    best_bid = yes_bids[0][0] / 100.0 if yes_bids else None
    best_ask = (1.0 - no_bids[0][0] / 100.0) if no_bids else None

    if best_bid is not None and best_ask is not None:
        return (best_bid + best_ask) / 2.0
    if best_bid is not None:
        return best_bid
    if best_ask is not None:
        return best_ask
    return None


def fee_adjusted_breakeven(mid, fee_rate, is_long):
    """Compute breakeven probability at current mid accounting for fees.

    For long YES: you profit (1-mid)(1-fee) if YES, lose mid if NO.
    Breakeven: prob = mid / [mid + (1-mid)(1-fee)]

    For short YES (long NO): you profit mid*(1-fee) if NO, lose (1-mid) if YES.
    Breakeven: prob = 1 - (1-mid) / [(1-mid) + mid*(1-fee)]
    """
    if fee_rate == 0:
        return mid
    if is_long:
        denom = mid + (1.0 - mid) * (1.0 - fee_rate)
        return mid / denom if denom > 0 else mid
    else:
        denom = (1.0 - mid) + mid * (1.0 - fee_rate)
        return 1.0 - (1.0 - mid) / denom if denom > 0 else mid


class PositionFeed:
    def __init__(self, config: FeedConfig = None, model_probs: dict = None):
        self.config = config or FeedConfig()
        self.model_probs = model_probs or {}
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = KalshiClient(self.config.kalshi)
            self._client.login()
        return self._client

    def get_positions(self) -> list[Position]:
        raw_positions = self.client.get_positions()
        positions = []
        for rp in raw_positions:
            ticker = rp.get("ticker", rp.get("market_ticker", ""))
            try:
                pos = self._normalize_kalshi(rp, ticker)
                if pos is not None:
                    positions.append(pos)
            except Exception:
                continue
        return positions

    def _normalize_kalshi(self, raw_pos, ticker) -> Position | None:
        quantity = raw_pos.get("position", 0)
        if quantity == 0:
            return None

        market = self.client.get_market(ticker)
        orderbook = self.client.get_orderbook(ticker)

        mid = compute_mid_from_orderbook(orderbook)
        if mid is None:
            last_price = market.get("last_price")
            mid = last_price / 100.0 if last_price else 0.5

        close_time = market.get("close_time", market.get("expiration_time", ""))
        resolves_at = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        tte_days = max((resolves_at - now).total_seconds() / 86400.0, 0.0)

        entry_price = raw_pos.get("average_price_paid", raw_pos.get("resting_orders_count", 0))
        if isinstance(entry_price, (int, float)) and entry_price > 1:
            entry_price = entry_price / 100.0

        market_prob = mid
        is_long = quantity > 0
        fee_rate = self.config.kalshi.fee_rate
        fab = fee_adjusted_breakeven(mid, fee_rate, is_long)

        event_ticker = market.get("event_ticker", market.get("series_ticker", ticker))

        model_prob = self.model_probs.get(ticker, market_prob)

        return Position(
            contract_id=ticker,
            platform="kalshi",
            canonical_event_id=event_ticker,
            quantity=quantity,
            entry_price=entry_price,
            current_mid=mid,
            market_prob=market_prob,
            model_prob=model_prob,
            edge=model_prob - market_prob,
            resolves_at=resolves_at,
            tte_days=tte_days,
            fee_adjusted_breakeven=fab,
        )


def build_position_from_data(
    contract_id, platform, canonical_event_id, quantity, entry_price,
    current_mid, resolves_at, fee_rate, model_prob=None,
):
    """Build a Position from pre-fetched data (useful for testing and offline use)."""
    now = datetime.now(timezone.utc)
    if isinstance(resolves_at, str):
        resolves_at = datetime.fromisoformat(resolves_at.replace("Z", "+00:00"))
    tte_days = max((resolves_at - now).total_seconds() / 86400.0, 0.0)

    market_prob = current_mid
    is_long = quantity > 0
    fab = fee_adjusted_breakeven(current_mid, fee_rate, is_long)
    if model_prob is None:
        model_prob = market_prob

    return Position(
        contract_id=contract_id,
        platform=platform,
        canonical_event_id=canonical_event_id,
        quantity=quantity,
        entry_price=entry_price,
        current_mid=current_mid,
        market_prob=market_prob,
        model_prob=model_prob,
        edge=model_prob - market_prob,
        resolves_at=resolves_at,
        tte_days=tte_days,
        fee_adjusted_breakeven=fab,
    )
