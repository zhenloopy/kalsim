import pytest
from src.liquidity import (
    compute_spread,
    compute_depth_at_best,
    compute_liquidation_slippage,
    compute_amihud,
    compute_position_vs_adv,
    classify_liquidity,
    compute_liquidity_metrics,
)


def make_orderbook(yes_bids, no_bids):
    """Build orderbook. Prices in cents, quantities as integers."""
    return {"yes": yes_bids, "no": no_bids}


class TestSpread:
    def test_basic_spread(self):
        # YES bid 55c, NO bid 40c → YES ask 60c. Valid non-crossed book.
        ob = make_orderbook([[55, 100]], [[40, 100]])
        spread_pct, bid, ask = compute_spread(ob)
        assert bid == 0.55
        assert ask == 0.60
        mid = (0.55 + 0.60) / 2.0
        expected = (0.60 - 0.55) / mid
        assert abs(spread_pct - expected) < 1e-10

    def test_tight_spread(self):
        ob = make_orderbook([[50, 100]], [[49, 100]])
        spread_pct, bid, ask = compute_spread(ob)
        assert bid == 0.50
        assert ask == 0.51
        expected = 0.01 / 0.505
        assert abs(spread_pct - expected) < 1e-10

    def test_wide_spread(self):
        ob = make_orderbook([[40, 10]], [[30, 10]])
        spread_pct, _, _ = compute_spread(ob)
        mid = (0.40 + 0.70) / 2.0
        expected = 0.30 / mid
        assert abs(spread_pct - expected) < 1e-10

    def test_empty_book(self):
        ob = make_orderbook([], [])
        spread_pct, _, _ = compute_spread(ob)
        assert spread_pct == float("inf")


class TestDepthAtBest:
    def test_basic(self):
        ob = make_orderbook([[55, 200]], [[45, 150]])
        bid_d, ask_d = compute_depth_at_best(ob)
        assert bid_d == 200
        assert ask_d == 150

    def test_empty(self):
        ob = make_orderbook([], [])
        bid_d, ask_d = compute_depth_at_best(ob)
        assert bid_d == 0
        assert ask_d == 0


class TestLiquidationSlippage:
    def test_full_fill_at_best(self):
        """Selling 50 into a bid of 100 at 55c. Mid = (0.55+0.52)/2 = 0.535.
        VWAP = 0.55, slippage = (0.535 - 0.55)*50 = negative → 0."""
        ob = make_orderbook([[55, 100]], [[48, 100]])
        slip = compute_liquidation_slippage(ob, 50)
        assert slip == 0.0 or slip >= 0

    def test_walking_the_book(self):
        """Sell 150 contracts into a 2-level bid: 100@55c + 100@50c.
        Mid = (0.55 + 0.52) / 2 = 0.535
        Fill 100 @ 0.55, fill 50 @ 0.50
        VWAP = (100*0.55 + 50*0.50) / 150 = 80/150 = 0.5333...
        Slippage = (0.535 - 0.5333) * 150 = 0.25"""
        ob = make_orderbook([[55, 100], [50, 100]], [[48, 100]])
        slip = compute_liquidation_slippage(ob, 150)
        vwap = (100 * 0.55 + 50 * 0.50) / 150
        mid = (0.55 + 0.52) / 2.0
        expected = (mid - vwap) * 150
        assert abs(slip - expected) < 1e-10

    def test_insufficient_depth(self):
        """Sell 200 into only 50 available. Unfilled portion at 0 (worst case)."""
        ob = make_orderbook([[60, 50]], [[40, 50]])
        slip = compute_liquidation_slippage(ob, 200)
        mid = (0.60 + 0.60) / 2.0
        vwap = (50 * 0.60 + 150 * 0.0) / 200
        expected = (mid - vwap) * 200
        assert abs(slip - expected) < 1e-10

    def test_short_position_slippage(self):
        """Buy back 50 (short position). Walk the ask (NO bid) side.
        NO bids at 45c → YES ask at 55c. Mid = (0.50 + 0.55)/2 = 0.525.
        VWAP = 0.55, slippage = (0.55 - 0.525) * 50 = 1.25"""
        ob = make_orderbook([[50, 100]], [[45, 100]])
        slip = compute_liquidation_slippage(ob, -50)
        mid = (0.50 + 0.55) / 2.0
        vwap = 0.55
        expected = (vwap - mid) * 50
        assert abs(slip - expected) < 1e-10

    def test_zero_position(self):
        ob = make_orderbook([[50, 100]], [[50, 100]])
        assert compute_liquidation_slippage(ob, 0) == 0.0


class TestAmihud:
    def test_basic(self):
        price_changes = [0.02, -0.01, 0.03]
        dollar_volumes = [1000, 2000, 500]
        result = compute_amihud(price_changes, dollar_volumes)
        expected = (0.02/1000 + 0.01/2000 + 0.03/500) / 3
        assert abs(result - expected) < 1e-12

    def test_zero_volume_skipped(self):
        result = compute_amihud([0.01, 0.02], [0, 1000])
        expected = 0.02 / 1000
        assert abs(result - expected) < 1e-12

    def test_no_data(self):
        assert compute_amihud(None, None) is None
        assert compute_amihud([], []) is None


class TestPositionVsAdv:
    def test_basic(self):
        result = compute_position_vs_adv(100, 0.55, 500.0)
        expected = (100 * 0.55) / 500.0
        assert abs(result - expected) < 1e-10

    def test_no_volume(self):
        assert compute_position_vs_adv(100, 0.5, None) is None
        assert compute_position_vs_adv(100, 0.5, 0) is None


class TestLiquidityFlags:
    def test_critical_tte(self):
        assert classify_liquidity(2.9, 0.01) == "CRITICAL"
        assert classify_liquidity(0, 0.01) == "CRITICAL"

    def test_watch_tte(self):
        assert classify_liquidity(13, 0.01) == "WATCH"
        assert classify_liquidity(7, 0.01) == "WATCH"

    def test_watch_spread(self):
        assert classify_liquidity(30, 0.06) == "WATCH"

    def test_normal(self):
        assert classify_liquidity(30, 0.02) == "NORMAL"
        assert classify_liquidity(14, 0.05) == "NORMAL"

    def test_boundary_critical(self):
        assert classify_liquidity(3, 0.01) == "WATCH"
        assert classify_liquidity(2.99, 0.01) == "CRITICAL"


class TestComputeLiquidityMetrics:
    def test_full_metrics(self):
        ob = make_orderbook([[55, 100], [50, 50]], [[45, 80]])
        m = compute_liquidity_metrics(
            "TEST-YES", ob, 30, 0.52, tte_days=20.0,
            price_changes=[0.01, 0.02], dollar_volumes=[500, 1000],
            avg_daily_volume=200.0,
        )
        assert m.contract_id == "TEST-YES"
        assert m.spread_pct > 0
        assert m.depth_at_best_bid == 100
        assert m.depth_at_best_ask == 80
        assert m.amihud is not None
        assert m.position_vs_adv is not None
        assert m.liquidation_slippage >= 0
        assert m.liquidity_flag == "NORMAL"
