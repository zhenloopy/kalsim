"""Tests for BookState — the shared in-memory market state.

Focus on orderbook delta application correctness, mid price derivation,
and position P&L computation since these are the critical paths.
"""
import pytest
from datetime import datetime, timezone, timedelta
from src.book_state import BookState, TickerData
from src.schema import Position


def _make_position(contract_id="TEST-YES", quantity=10, entry_price=0.50, mid=0.55):
    return Position(
        contract_id=contract_id,
        platform="kalshi",
        canonical_event_id="EVENT-1",
        quantity=quantity,
        entry_price=entry_price,
        current_mid=mid,
        market_prob=mid,
        model_prob=mid,
        edge=0.0,
        resolves_at=datetime.now(timezone.utc) + timedelta(days=30),
        tte_days=30.0,
        fee_adjusted_breakeven=0.52,
    )


class TestOrderbookSnapshotAndDelta:
    def test_snapshot_stores_levels(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 100], [48, 200]], [[55, 50], [57, 80]])
        ob = state.get_orderbook_for_api("T")
        assert len(ob["yes"]) == 2
        assert len(ob["no"]) == 2
        assert ob["yes"][0] == [50, 100]  # sorted desc by price

    def test_delta_adds_new_level(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 100]], [[55, 50]])
        state.apply_orderbook_delta("T", 49, 75, "yes")
        ob = state.get_orderbook_for_api("T")
        prices = {p for p, _ in ob["yes"]}
        assert 49 in prices

    def test_delta_modifies_existing_level(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 100]], [])
        state.apply_orderbook_delta("T", 50, -30, "yes")
        ob = state.get_orderbook_for_api("T")
        for p, q in ob["yes"]:
            if p == 50:
                assert q == 70

    def test_delta_removes_level_when_qty_zero(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 100]], [])
        state.apply_orderbook_delta("T", 50, -100, "yes")
        ob = state.get_orderbook_for_api("T")
        assert len(ob["yes"]) == 0

    def test_delta_removes_level_when_qty_negative(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 100]], [])
        state.apply_orderbook_delta("T", 50, -150, "yes")
        ob = state.get_orderbook_for_api("T")
        assert len(ob["yes"]) == 0

    def test_delta_on_no_side(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [], [[55, 50]])
        state.apply_orderbook_delta("T", 60, 30, "no")
        ob = state.get_orderbook_for_api("T")
        assert len(ob["no"]) == 2

    def test_delta_on_empty_book(self):
        """Delta arriving before snapshot should create the level."""
        state = BookState()
        state.apply_orderbook_delta("T", 50, 100, "yes")
        ob = state.get_orderbook_for_api("T")
        assert ob["yes"][0] == [50, 100]

    def test_snapshot_zero_qty_ignored(self):
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 0], [48, 100]], [])
        ob = state.get_orderbook_for_api("T")
        assert len(ob["yes"]) == 1
        assert ob["yes"][0][0] == 48


class TestMidPriceComputation:
    def test_mid_from_both_sides(self):
        state = BookState()
        # YES best bid = 50 (0.50), NO best bid = 55 (ask = 1 - 0.55 = 0.45)
        # Wait, that gives ask < bid. Let's use realistic values:
        # YES best bid = 42 cents, NO best bid = 56 cents → ask = 44 cents
        # mid = (0.42 + 0.44) / 2 = 0.43
        state.apply_orderbook_snapshot("T", [[42, 100]], [[56, 100]])
        mid = state.get_mid("T")
        assert mid is not None
        assert abs(mid - 0.43) < 0.01

    def test_mid_updates_position(self):
        state = BookState()
        pos = _make_position("T", mid=0.50)
        state.set_positions([pos])
        state.apply_orderbook_snapshot("T", [[42, 100]], [[56, 100]])
        # Position mid should be updated
        assert abs(state.positions[0].current_mid - 0.43) < 0.01

    def test_mid_none_for_unknown_ticker(self):
        state = BookState()
        assert state.get_mid("UNKNOWN") is None


class TestPositionPnL:
    def test_long_profit(self):
        state = BookState()
        pos = _make_position(quantity=10, entry_price=0.40, mid=0.60)
        state.set_positions([pos])
        # PnL = 10 * (0.60 - 0.40) = 2.0
        assert abs(state.get_position_pnl(pos) - 2.0) < 1e-10

    def test_long_loss(self):
        state = BookState()
        pos = _make_position(quantity=10, entry_price=0.60, mid=0.40)
        state.set_positions([pos])
        assert abs(state.get_position_pnl(pos) - (-2.0)) < 1e-10

    def test_short_profit(self):
        state = BookState()
        pos = _make_position(quantity=-10, entry_price=0.60, mid=0.40)
        state.set_positions([pos])
        # PnL = -10 * (0.40 - 0.60) = 2.0
        assert abs(state.get_position_pnl(pos) - 2.0) < 1e-10

    def test_total_pnl_sums_positions(self):
        state = BookState()
        p1 = _make_position("A", quantity=10, entry_price=0.40, mid=0.50)
        p2 = _make_position("B", quantity=-5, entry_price=0.70, mid=0.60)
        state.set_positions([p1, p2])
        # p1: 10*(0.50-0.40) = 1.0
        # p2: -5*(0.60-0.70) = 0.50
        expected = 1.0 + 0.50
        assert abs(state.get_total_pnl() - expected) < 1e-10

    def test_pnl_updates_when_mid_changes(self):
        state = BookState()
        pos = _make_position("T", quantity=10, entry_price=0.40, mid=0.50)
        state.set_positions([pos])
        assert abs(state.get_total_pnl() - 1.0) < 1e-10
        # Simulate orderbook update that changes mid
        state.apply_orderbook_snapshot("T", [[55, 100]], [[50, 100]])
        new_mid = state.positions[0].current_mid
        expected = 10 * (new_mid - 0.40)
        assert abs(state.get_total_pnl() - expected) < 1e-10


class TestFillHandling:
    def test_fill_increases_long_position(self):
        state = BookState()
        pos = _make_position("T", quantity=10)
        state.set_positions([pos])
        state.apply_fill("T", "yes", 5, 50)
        assert state.positions[0].quantity == 15

    def test_fill_decreases_short_position(self):
        state = BookState()
        pos = _make_position("T", quantity=-10)
        state.set_positions([pos])
        state.apply_fill("T", "no", 5, 50)
        assert state.positions[0].quantity == -15

    def test_fill_on_unknown_ticker_creates_position(self):
        state = BookState()
        pos = _make_position("T", quantity=10)
        state.set_positions([pos])
        new_ticker = state.apply_fill("UNKNOWN", "yes", 5, 50)
        assert new_ticker == "UNKNOWN"
        assert state.positions[0].quantity == 10
        assert len(state.positions) == 2
        assert state.positions[1].contract_id == "UNKNOWN"
        assert state.positions[1].quantity == 5
        assert state.positions[1].entry_price == 0.5

    def test_fill_on_unknown_ticker_no_side(self):
        state = BookState()
        new_ticker = state.apply_fill("NEW", "no", 3, 93)
        assert new_ticker == "NEW"
        assert len(state.positions) == 1
        assert state.positions[0].quantity == -3
        assert abs(state.positions[0].entry_price - 0.07) < 1e-10

    def test_fill_on_existing_returns_none(self):
        state = BookState()
        pos = _make_position("T", quantity=10)
        state.set_positions([pos])
        result = state.apply_fill("T", "yes", 5, 50)
        assert result is None


class TestCallbacks:
    def test_callback_fires_on_position_set(self):
        state = BookState()
        fired = []
        state.on_change(lambda: fired.append(True))
        state.set_positions([_make_position()])
        assert len(fired) == 1

    def test_callback_fires_on_delta(self):
        state = BookState()
        fired = []
        state.on_change(lambda: fired.append(True))
        state.apply_orderbook_delta("T", 50, 100, "yes")
        assert len(fired) >= 1

    def test_callback_exception_doesnt_break_state(self):
        state = BookState()
        def bad_callback():
            raise RuntimeError("oops")
        state.on_change(bad_callback)
        state.apply_orderbook_snapshot("T", [[50, 100]], [])
        assert state.get_mid("T") is not None


class TestEdgeCases:
    def test_orderbook_sorting_descending(self):
        """Verify levels are sorted best-first (highest price first)."""
        state = BookState()
        state.apply_orderbook_snapshot("T", [[10, 50], [50, 100], [30, 75]], [])
        ob = state.get_orderbook_for_api("T")
        prices = [p for p, _ in ob["yes"]]
        assert prices == sorted(prices, reverse=True)

    def test_many_rapid_deltas(self):
        """Simulate rapid-fire delta updates to verify consistency."""
        state = BookState()
        state.apply_orderbook_snapshot("T", [[50, 1000]], [])
        for i in range(100):
            state.apply_orderbook_delta("T", 50, -10, "yes")
        ob = state.get_orderbook_for_api("T")
        # 1000 - 100*10 = 0, level should be removed
        assert len(ob["yes"]) == 0

    def test_ws_status_tracking(self):
        state = BookState()
        assert state.ws_connected is False
        state.ws_connected = True
        assert state.ws_connected is True
