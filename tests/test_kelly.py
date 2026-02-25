import numpy as np
import pytest
from src.kelly import raw_kelly_fraction, kelly_optimize


class TestRawKelly:
    def test_analytical_formula(self):
        """f* = (p - q) / (1 - q) where p=model_prob, q=market_prob."""
        assert abs(raw_kelly_fraction(0.60, 0.50) - 0.20) < 1e-10
        assert abs(raw_kelly_fraction(0.70, 0.50) - 0.40) < 1e-10
        assert abs(raw_kelly_fraction(0.50, 0.50) - 0.0) < 1e-10

    def test_no_edge(self):
        assert raw_kelly_fraction(0.50, 0.50) == 0.0

    def test_negative_edge(self):
        """Negative edge → negative Kelly (don't bet, or bet the other side)."""
        assert raw_kelly_fraction(0.40, 0.50) < 0.0

    def test_market_prob_one(self):
        assert raw_kelly_fraction(0.99, 1.0) == 0.0


class TestKellyOptimizer:
    def _make_pos(self, contract_id, model_prob, market_prob, quantity=0, entry_price=0.50):
        return {
            "contract_id": contract_id,
            "model_prob": model_prob,
            "market_prob": market_prob,
            "quantity": quantity,
            "entry_price": entry_price,
        }

    def test_single_contract_recovers_analytical(self):
        """Single contract should produce fraction close to analytical Kelly * lambda."""
        pos = [self._make_pos("A", 0.70, 0.50)]
        result = kelly_optimize(pos, kelly_fraction=1.0, min_edge=0.01, per_contract_cap=1.0)
        expected = raw_kelly_fraction(0.70, 0.50)
        assert abs(result.target_fractions[0] - expected) < 0.01

    def test_fractional_kelly(self):
        pos = [self._make_pos("A", 0.70, 0.50)]
        result = kelly_optimize(pos, kelly_fraction=0.25, min_edge=0.01, per_contract_cap=1.0)
        expected = raw_kelly_fraction(0.70, 0.50) * 0.25
        assert abs(result.target_fractions[0] - expected) < 0.01

    def test_zero_edge_produces_zero(self):
        """All edges = 0 → all allocations = 0."""
        positions = [
            self._make_pos("A", 0.50, 0.50),
            self._make_pos("B", 0.60, 0.60),
            self._make_pos("C", 0.70, 0.70),
        ]
        result = kelly_optimize(positions)
        np.testing.assert_allclose(result.target_fractions, 0.0, atol=1e-10)

    def test_below_min_edge_filtered(self):
        """Contracts with edge < min_edge get zero allocation."""
        pos = [self._make_pos("A", 0.52, 0.50)]  # edge = 0.02 < 0.03
        result = kelly_optimize(pos, min_edge=0.03)
        assert result.target_fractions[0] == 0.0

    def test_per_contract_cap(self):
        pos = [self._make_pos("A", 0.90, 0.50)]  # huge edge
        result = kelly_optimize(pos, per_contract_cap=0.05, kelly_fraction=1.0, min_edge=0.01)
        assert abs(result.target_fractions[0]) <= 0.05 + 1e-10

    def test_liquidity_cap(self):
        """Position should not exceed liquidity cap."""
        pos = [self._make_pos("A", 0.80, 0.50)]
        result = kelly_optimize(
            pos, per_contract_cap=1.0, kelly_fraction=1.0, min_edge=0.01,
            liquidity_caps={"A": 0.10}, bankroll=1.0,
        )
        assert abs(result.target_fractions[0]) <= 0.10 + 1e-10

    def test_cluster_cap(self):
        """Positions in the same cluster should not exceed cluster cap combined."""
        positions = [
            self._make_pos("A", 0.80, 0.50),
            self._make_pos("B", 0.80, 0.50),
        ]
        result = kelly_optimize(
            positions,
            per_contract_cap=1.0, kelly_fraction=1.0, min_edge=0.01,
            cluster_assignments={"A": "macro", "B": "macro"},
            cluster_caps={"macro": 0.15},
        )
        total = np.sum(np.abs(result.target_fractions))
        assert total <= 0.15 + 1e-10

    def test_recommended_trades(self):
        """Recommended trade = target - current."""
        pos = [self._make_pos("A", 0.70, 0.50, quantity=10, entry_price=0.50)]
        result = kelly_optimize(pos, bankroll=100.0, kelly_fraction=0.25, min_edge=0.01,
                                per_contract_cap=1.0)
        current_frac = 10 * 0.50 / 100.0
        expected_trade = result.target_fractions[0] - current_frac
        assert abs(result.recommended_trades[0] - expected_trade) < 1e-10 or result.recommended_trades[0] == 0.0

    def test_rebalance_threshold(self):
        """Tiny trades below threshold are suppressed."""
        pos = [self._make_pos("A", 0.505, 0.50, quantity=100, entry_price=0.50)]
        result = kelly_optimize(pos, bankroll=10000.0, min_edge=0.001, rebalance_threshold=0.01)
        assert result.recommended_trades[0] == 0.0

    def test_with_simulated_returns(self):
        """Joint optimization with simulated returns."""
        rng = np.random.default_rng(42)
        pos = [
            self._make_pos("A", 0.65, 0.50),
            self._make_pos("B", 0.60, 0.50),
        ]
        n_sims = 5000
        returns = np.zeros((n_sims, 2))
        for i, p in enumerate(pos):
            resolves = rng.random(n_sims) < p["model_prob"]
            returns[:, i] = np.where(resolves, 1.0 - p["entry_price"], -p["entry_price"])

        result = kelly_optimize(
            pos, simulated_returns=returns,
            kelly_fraction=0.5, min_edge=0.01, per_contract_cap=0.20,
        )
        assert all(abs(f) <= 0.20 + 1e-6 for f in result.target_fractions)
        assert all(f > 0 for f in result.target_fractions)
