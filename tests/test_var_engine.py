import numpy as np
import pytest
from src.var_engine import simulate_pnl, run_dual_var


def make_single_position(quantity=100, entry_price=0.60, model_prob=0.60, market_prob=0.60):
    return [{"quantity": quantity, "entry_price": entry_price,
             "model_prob": model_prob, "market_prob": market_prob}]


class TestSingleContract:
    def test_var_high_prob_equals_full_position(self):
        """When market_prob > 0.95, the contract almost certainly resolves YES.
        For a long YES position, loss only occurs if it resolves NO.
        With p=0.97, only ~3% of sims resolve NO. VaR_95 should be near 0
        (since 95th percentile of losses is still in the winning region)."""
        pos = make_single_position(quantity=100, entry_price=0.60, model_prob=0.97)
        corr = np.array([[1.0]])
        result = simulate_pnl(pos, corr, n_sims=50_000, seed=42)
        # With 97% YES probability, the 95th percentile loss should be ≤ 0
        # (since 97% of outcomes are profitable)
        assert result.var_95 <= 0.01 * 100

    def test_var_low_prob_equals_full_loss(self):
        """When model_prob is very low (contract almost certainly resolves NO),
        a long YES position loses entry_price per contract with high probability.
        VaR_95 ≈ quantity * entry_price."""
        pos = make_single_position(quantity=100, entry_price=0.60, model_prob=0.02)
        corr = np.array([[1.0]])
        result = simulate_pnl(pos, corr, n_sims=50_000, seed=42)
        max_loss = 100 * 0.60
        assert abs(result.var_95 - max_loss) < max_loss * 0.05

    def test_fair_coin_var(self):
        """At model_prob=0.5, long YES at 0.5: each contract has equal
        chance of +0.5 or -0.5. With 100 contracts and no correlation to
        consider (single contract), VaR is just the loss in the losing state."""
        pos = make_single_position(quantity=1, entry_price=0.50, model_prob=0.50)
        corr = np.array([[1.0]])
        result = simulate_pnl(pos, corr, n_sims=100_000, seed=42)
        # Single binary: loss is either -0.5 (50%) or +0.5 (50%)
        # 95th percentile loss = 0.5
        assert abs(result.var_95 - 0.5) < 0.05


class TestSubadditivity:
    def test_cvar_subadditivity_independent(self):
        """CVaR of two independent portfolios should be ≤ sum of individual CVaRs.
        This is a fundamental property of coherent risk measures."""
        pos_a = [{"quantity": 50, "entry_price": 0.55, "model_prob": 0.50, "market_prob": 0.50}]
        pos_b = [{"quantity": 50, "entry_price": 0.45, "model_prob": 0.50, "market_prob": 0.50}]

        corr_single = np.array([[1.0]])
        corr_joint = np.eye(2)

        result_a = simulate_pnl(pos_a, corr_single, n_sims=50_000, seed=42)
        result_b = simulate_pnl(pos_b, corr_single, n_sims=50_000, seed=43)
        result_ab = simulate_pnl(pos_a + pos_b, corr_joint, n_sims=50_000, seed=44)

        assert result_ab.cvar_95 <= result_a.cvar_95 + result_b.cvar_95 + 1.0

    def test_var_subadditivity_independent(self):
        """VaR of combined independent portfolio ≤ sum of individual VaRs (approximately)."""
        pos_a = [{"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50}]
        pos_b = [{"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50}]

        corr1 = np.array([[1.0]])
        corr2 = np.eye(2)

        r_a = simulate_pnl(pos_a, corr1, n_sims=50_000, seed=42)
        r_b = simulate_pnl(pos_b, corr1, n_sims=50_000, seed=43)
        r_ab = simulate_pnl(pos_a + pos_b, corr2, n_sims=50_000, seed=44)

        # With diversification, combined VaR should be less than sum
        assert r_ab.var_95 <= r_a.var_95 + r_b.var_95 + 1.0


class TestCorrelationEffect:
    def test_perfect_correlation_no_diversification(self):
        """With perfect correlation, combined VaR ≈ sum of individual VaRs."""
        pos = [
            {"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50},
            {"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50},
        ]
        corr_perfect = np.ones((2, 2))
        corr_indep = np.eye(2)

        r_perfect = simulate_pnl(pos, corr_perfect, n_sims=50_000, seed=42)
        r_indep = simulate_pnl(pos, corr_indep, n_sims=50_000, seed=42)

        assert r_perfect.var_95 > r_indep.var_95 * 0.9


class TestDualVar:
    def test_dual_produces_two_results(self):
        pos = make_single_position(model_prob=0.65, market_prob=0.55)
        corr = np.array([[1.0]])
        model_r, market_r = run_dual_var(pos, corr, n_sims=10_000, seed=42)
        assert model_r.label == "model_prob"
        assert market_r.label == "market_prob"

    def test_belief_divergence_visible(self):
        """When model_prob >> market_prob, model believes losses are rarer.
        With model_prob=0.98, loss prob=2% < 5%, so VaR_95 reflects profit.
        With market_prob=0.50, loss prob=50% > 5%, so VaR_95 = full loss."""
        pos = [{"quantity": 100, "entry_price": 0.50, "model_prob": 0.98, "market_prob": 0.50}]
        corr = np.array([[1.0]])
        model_r, market_r = run_dual_var(pos, corr, n_sims=50_000, seed=42)
        assert model_r.var_95 < market_r.var_95


class TestSlippage:
    def test_slippage_increases_tail_losses(self):
        pos = make_single_position(quantity=100, entry_price=0.50, model_prob=0.50)
        corr = np.array([[1.0]])
        r_no_slip = simulate_pnl(pos, corr, n_sims=50_000, seed=42)
        r_with_slip = simulate_pnl(pos, corr, n_sims=50_000, seed=42,
                                    slippage_per_position=np.array([5.0]))
        assert r_with_slip.var_99 >= r_no_slip.var_99


class TestComponentVar:
    def test_component_var_shape(self):
        pos = [
            {"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50},
            {"quantity": 50, "entry_price": 0.60, "model_prob": 0.60, "market_prob": 0.60},
        ]
        corr = np.eye(2)
        result = simulate_pnl(pos, corr, n_sims=10_000, seed=42)
        assert result.component_var.shape == (2,)

    def test_component_var_sums_approximate_var(self):
        """Sum of component VaRs should approximate total VaR_95."""
        pos = [
            {"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50},
            {"quantity": 100, "entry_price": 0.50, "model_prob": 0.50, "market_prob": 0.50},
        ]
        corr = np.eye(2)
        result = simulate_pnl(pos, corr, n_sims=50_000, seed=42)
        # Component VaR sum should be close to total VaR (they are computed
        # from the same tail scenarios)
        assert abs(np.sum(result.component_var) - result.var_95) < result.var_95 * 0.3


class TestEmptyPortfolio:
    def test_empty(self):
        result = simulate_pnl([], np.array([[]]), n_sims=1000)
        assert result.var_95 == 0
        assert result.var_99 == 0
