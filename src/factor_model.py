import numpy as np
from sklearn.covariance import LedoitWolf
from dataclasses import dataclass


@dataclass
class FactorModelResult:
    loadings: np.ndarray          # B: (N, k) factor loading matrix
    factor_cov: np.ndarray        # Sigma_F: (k, k) factor covariance
    idiosyncratic_var: np.ndarray # Sigma_epsilon: (N,) diagonal idiosyncratic variances
    explained_variance: np.ndarray # per-factor explained variance ratio
    contract_ids: list[str]
    n_factors: int


def prices_to_logit(prices: np.ndarray) -> np.ndarray:
    """Transform probabilities to log-odds: L = log(p / (1-p))."""
    clipped = np.clip(prices, 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def filter_extreme_prices(prices: np.ndarray, low=0.05, high=0.95):
    """Mask out rows where any contract has extreme price (near 0 or 1).
    Returns filtered price matrix and mask of kept rows."""
    mask = np.all((prices >= low) & (prices <= high), axis=1)
    return prices[mask], mask


def estimate_factor_model(
    daily_prices: np.ndarray,
    contract_ids: list[str],
    n_factors: int | None = None,
    max_factors: int = 4,
    min_factors: int = 2,
    min_explained: float = 0.5,
):
    """Estimate PCA factor model from daily contract price history.

    daily_prices: (T, N) matrix of daily prices in [0,1]
    contract_ids: list of N contract identifiers
    n_factors: force specific number of factors (None = auto-select)
    """
    filtered, _ = filter_extreme_prices(daily_prices)
    if filtered.shape[0] < 10:
        raise ValueError(f"Insufficient data after filtering: {filtered.shape[0]} days")

    logit_prices = prices_to_logit(filtered)
    delta_logit = np.diff(logit_prices, axis=0)

    n_obs, n_contracts = delta_logit.shape
    if n_contracts < 2:
        raise ValueError(f"Need at least 2 contracts, got {n_contracts}")

    lw = LedoitWolf()
    lw.fit(delta_logit)
    shrunk_cov = lw.covariance_

    eigenvalues, eigenvectors = np.linalg.eigh(shrunk_cov)
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    total_var = np.sum(eigenvalues)
    explained_ratios = eigenvalues / total_var

    if n_factors is None:
        cumulative = np.cumsum(explained_ratios)
        n_factors = min_factors
        for k in range(min_factors, max_factors + 1):
            n_factors = k
            if cumulative[k - 1] >= min_explained:
                break

    n_factors = min(n_factors, n_contracts, max_factors)
    n_factors = max(n_factors, 1)

    # B = eigenvectors scaled by sqrt(eigenvalue) so that Cov(returns) ≈ B Σ_F B' + Σ_ε
    # With PCA: eigenvectors are the loadings, eigenvalues are the variances
    B = eigenvectors[:, :n_factors]  # (N, k)
    factor_variances = eigenvalues[:n_factors]
    sigma_f = np.diag(factor_variances)  # (k, k)

    reconstructed = B @ sigma_f @ B.T
    residual = shrunk_cov - reconstructed
    sigma_epsilon = np.maximum(np.diag(residual), 0.0)

    return FactorModelResult(
        loadings=B,
        factor_cov=sigma_f,
        idiosyncratic_var=sigma_epsilon,
        explained_variance=explained_ratios[:n_factors],
        contract_ids=contract_ids,
        n_factors=n_factors,
    )


def reconstruct_covariance(result: FactorModelResult) -> np.ndarray:
    """Reconstruct full covariance from factor model: B Σ_F B' + diag(Σ_ε)."""
    return result.loadings @ result.factor_cov @ result.loadings.T + np.diag(result.idiosyncratic_var)
