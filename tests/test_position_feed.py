import pytest
import math
from datetime import datetime, timezone, timedelta
from src.schema import Position
from src.position_feed import (
    compute_mid_from_orderbook,
    fee_adjusted_breakeven,
    build_position_from_data,
)


class TestFeeAdjustedBreakeven:
    """Fee-adjusted breakeven must satisfy the zero-EV equation.
    For long: prob * (1-mid)(1-fee) - (1-prob) * mid = 0
    Solving: prob = mid / [mid + (1-mid)(1-fee)]
    """

    def test_long_basic(self):
        mid, fee = 0.60, 0.07
        be = fee_adjusted_breakeven(mid, fee, is_long=True)
        expected = mid / (mid + (1.0 - mid) * (1.0 - fee))
        assert abs(be - expected) < 1e-10

    def test_short_basic(self):
        mid, fee = 0.60, 0.07
        be = fee_adjusted_breakeven(mid, fee, is_long=False)
        expected = 1.0 - (1.0 - mid) / ((1.0 - mid) + mid * (1.0 - fee))
        assert abs(be - expected) < 1e-10

    def test_zero_fee_is_identity(self):
        for mid in [0.1, 0.5, 0.9]:
            assert fee_adjusted_breakeven(mid, 0.0, True) == mid
            assert fee_adjusted_breakeven(mid, 0.0, False) == mid

    def test_long_breakeven_higher_than_mid(self):
        """With fees, long YES needs a higher probability to break even."""
        for mid in [0.2, 0.5, 0.8]:
            be = fee_adjusted_breakeven(mid, 0.07, is_long=True)
            assert be > mid

    def test_short_breakeven_lower_than_mid(self):
        """With fees, short YES (long NO) needs a lower probability to break even."""
        for mid in [0.2, 0.5, 0.8]:
            be = fee_adjusted_breakeven(mid, 0.07, is_long=False)
            assert be < mid

    def test_zero_ev_identity_long(self):
        """Verify breakeven satisfies the zero-EV equation directly."""
        mid, fee = 0.45, 0.10
        prob = fee_adjusted_breakeven(mid, fee, is_long=True)
        ev = prob * (1 - mid) * (1 - fee) - (1 - prob) * mid
        assert abs(ev) < 1e-10

    def test_zero_ev_identity_short(self):
        """Verify breakeven satisfies the zero-EV equation for short."""
        mid, fee = 0.70, 0.05
        prob = fee_adjusted_breakeven(mid, fee, is_long=False)
        ev = (1 - prob) * mid * (1 - fee) - prob * (1 - mid)
        assert abs(ev) < 1e-10

    def test_symmetry_at_half(self):
        """At mid=0.5, long and short breakevens should be symmetric around 0.5."""
        fee = 0.07
        be_long = fee_adjusted_breakeven(0.5, fee, is_long=True)
        be_short = fee_adjusted_breakeven(0.5, fee, is_long=False)
        assert abs(be_long - (1.0 - be_short)) < 1e-10


class TestComputeMid:
    def test_basic_mid(self):
        ob = {"yes": [[55, 10]], "no": [[45, 10]]}
        mid = compute_mid_from_orderbook(ob)
        assert abs(mid - 0.55) < 1e-10

    def test_only_bid(self):
        ob = {"yes": [[40, 5]], "no": []}
        mid = compute_mid_from_orderbook(ob)
        assert abs(mid - 0.40) < 1e-10

    def test_only_ask(self):
        ob = {"yes": [], "no": [[30, 5]]}
        mid = compute_mid_from_orderbook(ob)
        assert abs(mid - 0.70) < 1e-10

    def test_empty_book(self):
        assert compute_mid_from_orderbook({"yes": [], "no": []}) is None


class TestPositionSchema:
    def _make_position(self, **overrides):
        now = datetime.now(timezone.utc)
        defaults = dict(
            contract_id="TEST-YES",
            platform="kalshi",
            canonical_event_id="TEST",
            quantity=10,
            entry_price=0.55,
            current_mid=0.60,
            resolves_at=now + timedelta(days=7),
            fee_rate=0.07,
        )
        defaults.update(overrides)
        return build_position_from_data(**defaults)

    def test_schema_fields_present(self):
        pos = self._make_position()
        required = [
            "contract_id", "platform", "canonical_event_id", "quantity",
            "entry_price", "current_mid", "market_prob", "model_prob",
            "edge", "resolves_at", "tte_days", "fee_adjusted_breakeven",
        ]
        for field in required:
            assert hasattr(pos, field), f"Missing field: {field}"

    def test_market_prob_equals_mid(self):
        pos = self._make_position(current_mid=0.65)
        assert pos.market_prob == 0.65

    def test_model_prob_defaults_to_market(self):
        pos = self._make_position(current_mid=0.60)
        assert pos.model_prob == pos.market_prob

    def test_model_prob_override(self):
        pos = self._make_position(current_mid=0.60, model_prob=0.70)
        assert pos.model_prob == 0.70
        assert abs(pos.edge - 0.10) < 1e-10

    def test_edge_computation(self):
        pos = self._make_position(current_mid=0.50, model_prob=0.55)
        assert abs(pos.edge - 0.05) < 1e-10

    def test_tte_positive(self):
        pos = self._make_position(resolves_at=datetime.now(timezone.utc) + timedelta(days=30))
        assert pos.tte_days > 29.0

    def test_tte_expired(self):
        pos = self._make_position(resolves_at=datetime.now(timezone.utc) - timedelta(days=1))
        assert pos.tte_days == 0.0

    def test_canonical_event_groups_contracts(self):
        """Two contracts from the same event should share canonical_event_id."""
        p1 = self._make_position(contract_id="FED-HOLD-YES", canonical_event_id="FED-MARCH")
        p2 = self._make_position(contract_id="FED-HIKE-YES", canonical_event_id="FED-MARCH")
        assert p1.canonical_event_id == p2.canonical_event_id == "FED-MARCH"
        assert p1.contract_id != p2.contract_id

    def test_fee_adjusted_breakeven_in_schema(self):
        """fee_adjusted_breakeven should be consistent with the standalone function."""
        pos = self._make_position(current_mid=0.60, quantity=10)
        expected = fee_adjusted_breakeven(0.60, 0.07, is_long=True)
        assert abs(pos.fee_adjusted_breakeven - expected) < 1e-10

    def test_negative_quantity_short_breakeven(self):
        pos = self._make_position(current_mid=0.60, quantity=-5)
        expected = fee_adjusted_breakeven(0.60, 0.07, is_long=False)
        assert abs(pos.fee_adjusted_breakeven - expected) < 1e-10
