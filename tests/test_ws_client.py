"""Tests for WebSocket client message handling.

Tests the message parsing and BookState integration without requiring
an actual websocket connection. The _handle_message method is the critical
path — it converts raw WS messages into BookState mutations.
"""
import pytest
from unittest.mock import MagicMock
from src.ws_client import KalshiWS
from src.book_state import BookState
from src.config import KalshiConfig


def _make_ws_client():
    """Create a WS client with mock config (no actual connection)."""
    config = MagicMock()
    config.key_id = "test_key"
    config.private_key = ""
    config.base_url = "https://api.elections.kalshi.com/trade-api/v2"
    state = BookState()
    # Skip private key loading by creating client directly with mocked internals
    client = object.__new__(KalshiWS)
    client.config = config
    client.book_state = state
    client._ws = None
    client._running = False
    client._sub_id = 0
    client._reconnect_delay = 1.0
    client._max_reconnect_delay = 30.0
    client._task = None
    client._private_key = MagicMock()
    client._key_id = "test_key"
    client._ws_url = "wss://test/trade-api/ws/v2"
    return client, state


class TestHandleOrderbookSnapshot:
    def test_snapshot_populates_book(self):
        ws, state = _make_ws_client()
        msg = {
            "type": "orderbook_snapshot",
            "sid": 1,
            "seq": 1,
            "msg": {
                "market_ticker": "TEST-YES",
                "yes": [[50, 100], [48, 200]],
                "no": [[55, 50]],
            }
        }
        ws._handle_message(msg)
        ob = state.get_orderbook_for_api("TEST-YES")
        assert ob is not None
        assert len(ob["yes"]) == 2
        assert len(ob["no"]) == 1

    def test_snapshot_overwrites_previous(self):
        ws, state = _make_ws_client()
        ws._handle_message({
            "type": "orderbook_snapshot",
            "msg": {"market_ticker": "T", "yes": [[50, 100]], "no": []}
        })
        ws._handle_message({
            "type": "orderbook_snapshot",
            "msg": {"market_ticker": "T", "yes": [[60, 200]], "no": []}
        })
        ob = state.get_orderbook_for_api("T")
        assert ob["yes"][0] == [60, 200]


class TestHandleOrderbookDelta:
    def test_delta_updates_level(self):
        ws, state = _make_ws_client()
        ws._handle_message({
            "type": "orderbook_snapshot",
            "msg": {"market_ticker": "T", "yes": [[50, 100]], "no": []}
        })
        ws._handle_message({
            "type": "orderbook_delta",
            "msg": {"market_ticker": "T", "price": 50, "delta": 50, "side": "yes"}
        })
        ob = state.get_orderbook_for_api("T")
        for p, q in ob["yes"]:
            if p == 50:
                assert q == 150

    def test_delta_sequence_consistency(self):
        """Apply a series of deltas and verify final state."""
        ws, state = _make_ws_client()
        ws._handle_message({
            "type": "orderbook_snapshot",
            "msg": {"market_ticker": "T", "yes": [[50, 100]], "no": [[55, 80]]}
        })
        deltas = [
            {"price": 50, "delta": -20, "side": "yes"},
            {"price": 49, "delta": 50, "side": "yes"},
            {"price": 55, "delta": -80, "side": "no"},  # removes level
            {"price": 60, "delta": 30, "side": "no"},
        ]
        for d in deltas:
            ws._handle_message({"type": "orderbook_delta", "msg": {"market_ticker": "T", **d}})

        ob = state.get_orderbook_for_api("T")
        yes_dict = {p: q for p, q in ob["yes"]}
        no_dict = {p: q for p, q in ob["no"]}
        assert yes_dict[50] == 80
        assert yes_dict[49] == 50
        assert 55 not in no_dict
        assert no_dict[60] == 30


class TestHandleTicker:
    def test_ticker_updates_data(self):
        ws, state = _make_ws_client()
        ws._handle_message({
            "type": "ticker",
            "msg": {
                "market_ticker": "T",
                "yes_price": 55,
                "volume": 1000,
                "open_interest": 500,
            }
        })
        td = state.ticker_data.get("T")
        assert td is not None
        assert td.last_price == 0.55
        assert td.volume == 1000
        assert td.open_interest == 500


class TestHandleFill:
    def test_fill_updates_position(self):
        ws, state = _make_ws_client()
        from datetime import datetime, timezone, timedelta
        from src.schema import Position
        pos = Position(
            contract_id="T", platform="kalshi", canonical_event_id="E",
            quantity=10, entry_price=0.50, current_mid=0.55,
            market_prob=0.55, model_prob=0.55, edge=0.0,
            resolves_at=datetime.now(timezone.utc) + timedelta(days=30),
            tte_days=30.0, fee_adjusted_breakeven=0.52,
        )
        state.set_positions([pos])
        ws._handle_message({
            "type": "fill",
            "msg": {"market_ticker": "T", "side": "yes", "count": 5, "yes_price": 50}
        })
        assert state.positions[0].quantity == 15


class TestHandleError:
    def test_error_message_doesnt_crash(self):
        ws, state = _make_ws_client()
        ws._handle_message({
            "type": "error",
            "msg": {"code": 5, "msg": "Invalid subscription"}
        })
        # Should just log, not crash

    def test_unknown_message_type_ignored(self):
        ws, state = _make_ws_client()
        ws._handle_message({"type": "unknown_type", "msg": {}})


class TestMidPriceIntegration:
    def test_orderbook_updates_position_mid(self):
        """Verify that an orderbook snapshot flowing through WS → BookState
        correctly updates the position's mid and edge."""
        ws, state = _make_ws_client()
        from datetime import datetime, timezone, timedelta
        from src.schema import Position
        pos = Position(
            contract_id="T", platform="kalshi", canonical_event_id="E",
            quantity=10, entry_price=0.50, current_mid=0.50,
            market_prob=0.50, model_prob=0.55, edge=0.05,
            resolves_at=datetime.now(timezone.utc) + timedelta(days=30),
            tte_days=30.0, fee_adjusted_breakeven=0.52,
        )
        state.set_positions([pos])

        # YES bid=60, NO bid=35 → ask = 1-0.35 = 0.65, mid = (0.60+0.65)/2 = 0.625
        ws._handle_message({
            "type": "orderbook_snapshot",
            "msg": {"market_ticker": "T", "yes": [[60, 100]], "no": [[35, 100]]}
        })
        assert abs(state.positions[0].current_mid - 0.625) < 0.01
        # Edge should be model_prob - new_market_prob
        assert abs(state.positions[0].edge - (0.55 - 0.625)) < 0.01
