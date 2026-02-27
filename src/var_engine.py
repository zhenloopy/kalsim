import numpy as np
from scipy.stats import norm
from dataclasses import dataclass


@dataclass
class VaRResult:
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    p_ruin: float
    component_var: np.ndarray
    pnl_distribution: np.ndarray
    label: str


def simulate_pnl(
    positions: list[dict],
    correlation_matrix: np.ndarray,
    n_sims: int = 100_000,
    use_model_prob: bool = True,
    slippage_per_position: np.ndarray | None = None,
    slippage_tail_pct: float = 0.05,
    seed: int | None = None,
):
    """Monte Carlo P&L simulation for a portfolio of binary contracts.

    positions: list of dicts with keys:
        - quantity: int (positive = long YES)
        - entry_price: float in [0,1]
        - model_prob: float in [0,1]
        - market_prob: float in [0,1]
    correlation_matrix: (N, N) covariance/correlation matrix for correlated draws
    slippage_per_position: (N,) slippage cost per position, added in tail scenarios
    """
    n = len(positions)
    if n == 0:
        return VaRResult(0, 0, 0, 0, 0, np.array([]), np.array([0.0] * n_sims), "empty")

    rng = np.random.default_rng(seed)

    probs = np.array([p["model_prob"] if use_model_prob else p["market_prob"] for p in positions])
    quantities = np.array([p["quantity"] for p in positions], dtype=float)
    entry_prices = np.array([p["entry_price"] for p in positions])

    # Draw correlated standard normals
    try:
        L = np.linalg.cholesky(correlation_matrix)
    except np.linalg.LinAlgError:
        eigenvalues, eigenvectors = np.linalg.eigh(correlation_matrix)
        eigenvalues = np.maximum(eigenvalues, 1e-10)
        L = eigenvectors @ np.diag(np.sqrt(eigenvalues))

    Z = rng.standard_normal((n_sims, n))
    correlated_Z = Z @ L.T

    # Probability integral transform
    U = norm.cdf(correlated_Z)

    # Binary resolution: contract resolves YES if U < prob
    resolves_yes = U < probs[np.newaxis, :]  # (n_sims, n)

    # P&L per contract per simulation
    # Long YES at entry_price p: if YES → profit = (1-p), if NO → loss = -p
    # Short YES (qty < 0): if YES → loss = -(1-p), if NO → profit = p
    pnl_if_yes = 1.0 - entry_prices   # profit per contract if resolves YES
    pnl_if_no = -entry_prices          # loss per contract if resolves NO

    per_contract_pnl = np.where(resolves_yes, pnl_if_yes, pnl_if_no)  # (n_sims, n)
    position_pnl = per_contract_pnl * quantities[np.newaxis, :]  # scale by quantity and direction

    portfolio_pnl = np.sum(position_pnl, axis=1)  # (n_sims,)

    # Add slippage in tail scenarios
    if slippage_per_position is not None:
        tail_threshold = np.percentile(portfolio_pnl, slippage_tail_pct * 100)
        tail_mask = portfolio_pnl <= tail_threshold
        total_slippage = np.sum(slippage_per_position)
        portfolio_pnl[tail_mask] -= total_slippage

    # Losses are negative P&L; VaR is reported as positive loss amounts
    losses = -portfolio_pnl
    var_95 = float(np.percentile(losses, 95))
    var_99 = float(np.percentile(losses, 99))
    cvar_95 = float(np.mean(losses[losses >= np.percentile(losses, 95)]))
    cvar_99 = float(np.mean(losses[losses >= np.percentile(losses, 99)]))

    # Max loss per position: long loses entry_price if NO, short loses (1-entry) if YES
    max_loss_per_pos = np.where(
        quantities > 0,
        np.abs(quantities) * entry_prices,
        np.abs(quantities) * (1.0 - entry_prices),
    )
    total_at_risk = float(np.sum(max_loss_per_pos))
    p_ruin = float(np.mean(losses >= total_at_risk)) if total_at_risk > 0 else 0.0

    # Component VaR: marginal contribution of each position
    var_95_idx = np.argsort(losses)[-int(n_sims * 0.05):]
    component_var = np.mean(-position_pnl[var_95_idx], axis=0)

    label = "model_prob" if use_model_prob else "market_prob"

    return VaRResult(
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        p_ruin=p_ruin,
        component_var=component_var,
        pnl_distribution=portfolio_pnl,
        label=label,
    )


def run_dual_var(positions, correlation_matrix, n_sims=100_000, **kwargs):
    """Run VaR twice: once with model_prob, once with market_prob."""
    model_result = simulate_pnl(positions, correlation_matrix, n_sims, use_model_prob=True, **kwargs)
    market_result = simulate_pnl(positions, correlation_matrix, n_sims, use_model_prob=False, **kwargs)
    return model_result, market_result
