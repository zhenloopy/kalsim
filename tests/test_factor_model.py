import numpy as np
import pytest
from sklearn.covariance import LedoitWolf
from src.factor_model import (
    prices_to_logit,
    filter_extreme_prices,
    estimate_factor_model,
    reconstruct_covariance,
)


def make_synthetic_prices(n_days=200, n_contracts=6, seed=42):
    """Generate synthetic correlated price paths in (0.05, 0.95).
    Uses a known factor structure so we can verify recovery."""
    rng = np.random.default_rng(seed)
    k = 2
    B_true = rng.standard_normal((n_contracts, k)) * 0.3
    factors = rng.standard_normal((n_days, k))
    noise = rng.standard_normal((n_days, n_contracts)) * 0.1
    logit_levels = np.cumsum(factors @ B_true.T + noise, axis=0)
    logit_levels -= logit_levels.mean(axis=0)
    prices = 1.0 / (1.0 + np.exp(-logit_levels))
    prices = np.clip(prices, 0.06, 0.94)
    return prices


class TestLogitTransform:
    def test_basic_values(self):
        p = np.array([0.5, 0.25, 0.75])
        L = prices_to_logit(p)
        assert abs(L[0]) < 1e-10
        assert L[1] < 0
        assert L[2] > 0

    def test_inverse(self):
        p = np.array([0.1, 0.3, 0.7, 0.9])
        L = prices_to_logit(p)
        recovered = 1.0 / (1.0 + np.exp(-L))
        np.testing.assert_allclose(recovered, p, atol=1e-6)

    def test_extreme_clipping(self):
        p = np.array([0.0, 1.0])
        L = prices_to_logit(p)
        assert np.all(np.isfinite(L))


class TestFilterExtremes:
    def test_filters_near_zero(self):
        prices = np.array([[0.5, 0.6], [0.03, 0.6], [0.4, 0.7]])
        filtered, mask = filter_extreme_prices(prices)
        assert filtered.shape[0] == 2
        assert not mask[1]

    def test_filters_near_one(self):
        prices = np.array([[0.5, 0.96], [0.5, 0.7]])
        filtered, mask = filter_extreme_prices(prices)
        assert filtered.shape[0] == 1


class TestFactorModel:
    def test_reconstruction_within_shrinkage_tolerance(self):
        """B·Σ_F·B' + Σ_ε must reconstruct the Ledoit-Wolf shrunk covariance."""
        prices = make_synthetic_prices(n_days=200, n_contracts=6)
        contract_ids = [f"C{i}" for i in range(6)]
        result = estimate_factor_model(prices, contract_ids, n_factors=2)

        reconstructed = reconstruct_covariance(result)

        # Compute the actual shrunk cov for comparison
        filtered, _ = filter_extreme_prices(prices)
        logit = prices_to_logit(filtered)
        delta = np.diff(logit, axis=0)
        lw = LedoitWolf().fit(delta)
        shrunk_cov = lw.covariance_

        # With 2 factors on 6 contracts, residual should be small but nonzero
        diff = np.abs(reconstructed - shrunk_cov)
        # The diagonal should reconstruct exactly (by construction)
        np.testing.assert_allclose(np.diag(reconstructed), np.diag(shrunk_cov), atol=1e-10)
        # Off-diagonal may differ by the idiosyncratic contribution dropped from PCA
        assert np.max(diff) < 0.5 * np.max(np.abs(shrunk_cov))

    def test_idiosyncratic_nonnegative(self):
        prices = make_synthetic_prices()
        result = estimate_factor_model(prices, [f"C{i}" for i in range(6)])
        assert np.all(result.idiosyncratic_var >= 0)

    def test_factor_count_auto(self):
        prices = make_synthetic_prices(n_contracts=6)
        result = estimate_factor_model(prices, [f"C{i}" for i in range(6)])
        assert 2 <= result.n_factors <= 4

    def test_factor_count_forced(self):
        prices = make_synthetic_prices(n_contracts=6)
        result = estimate_factor_model(prices, [f"C{i}" for i in range(6)], n_factors=3)
        assert result.n_factors == 3

    def test_explained_variance_sums_less_than_one(self):
        prices = make_synthetic_prices()
        result = estimate_factor_model(prices, [f"C{i}" for i in range(6)])
        assert np.sum(result.explained_variance) <= 1.0 + 1e-10

    def test_loadings_shape(self):
        prices = make_synthetic_prices(n_contracts=8)
        result = estimate_factor_model(prices, [f"C{i}" for i in range(8)], n_factors=3)
        assert result.loadings.shape == (8, 3)
        assert result.factor_cov.shape == (3, 3)
        assert result.idiosyncratic_var.shape == (8,)

    def test_insufficient_data_raises(self):
        prices = np.array([[0.5, 0.6]] * 5)
        with pytest.raises(ValueError, match="Insufficient data"):
            estimate_factor_model(prices, ["A", "B"])

    def test_stability_across_subsamples(self):
        """Factor loadings should be qualitatively stable across rolling windows."""
        prices = make_synthetic_prices(n_days=300, n_contracts=5, seed=99)
        ids = [f"C{i}" for i in range(5)]
        r1 = estimate_factor_model(prices[:200], ids, n_factors=2)
        r2 = estimate_factor_model(prices[50:250], ids, n_factors=2)

        # Sign of loadings can flip; compare absolute correlations
        for j in range(2):
            corr = abs(np.corrcoef(r1.loadings[:, j], r2.loadings[:, j])[0, 1])
            assert corr > 0.5, f"Factor {j} unstable: corr={corr:.3f}"

    def test_diagonal_reconstruction_exact(self):
        """By construction, diagonal of reconstructed cov should equal diagonal of shrunk cov."""
        prices = make_synthetic_prices(n_days=150, n_contracts=4)
        ids = [f"C{i}" for i in range(4)]
        result = estimate_factor_model(prices, ids, n_factors=2)
        reconstructed = reconstruct_covariance(result)

        filtered, _ = filter_extreme_prices(prices)
        delta = np.diff(prices_to_logit(filtered), axis=0)
        shrunk_diag = np.diag(LedoitWolf().fit(delta).covariance_)

        np.testing.assert_allclose(np.diag(reconstructed), shrunk_diag, atol=1e-10)
