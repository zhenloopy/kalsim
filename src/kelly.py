import numpy as np
from scipy.optimize import minimize
from dataclasses import dataclass


@dataclass
class KellyResult:
    target_fractions: np.ndarray
    raw_kelly: np.ndarray
    recommended_trades: np.ndarray
    contract_ids: list[str]


def raw_kelly_fraction(model_prob, market_prob):
    """Analytical Kelly fraction for a single binary contract.
    f* = (model_prob - market_prob) / (1 - market_prob)"""
    if market_prob >= 1.0:
        return 0.0
    return (model_prob - market_prob) / (1.0 - market_prob)


def kelly_optimize(
    positions: list[dict],
    simulated_returns: np.ndarray | None = None,
    bankroll: float = 1.0,
    kelly_fraction: float = 0.25,
    min_edge: float = 0.03,
    per_contract_cap: float = 0.05,
    cluster_caps: dict[str, float] | None = None,
    cluster_assignments: dict[str, str] | None = None,
    default_cluster_cap: float = 0.15,
    liquidity_caps: dict[str, float] | None = None,
    rebalance_threshold: float = 0.005,
):
    """Compute optimal Kelly allocations.

    positions: list of dicts with keys:
        - contract_id, model_prob, market_prob, quantity, entry_price
    simulated_returns: (n_sims, n_positions) matrix of per-simulation returns
        If None, uses analytical Kelly fractions.
    """
    n = len(positions)
    contract_ids = [p["contract_id"] for p in positions]

    raw = np.array([
        raw_kelly_fraction(p["model_prob"], p["market_prob"]) for p in positions
    ])

    edges = np.array([p["model_prob"] - p["market_prob"] for p in positions])
    has_edge = np.abs(edges) >= min_edge
    raw = raw * has_edge

    if simulated_returns is not None and simulated_returns.shape[1] == n:
        target = _optimize_joint_kelly(
            simulated_returns, raw, kelly_fraction,
            per_contract_cap, cluster_caps, cluster_assignments,
            default_cluster_cap, liquidity_caps, contract_ids, bankroll,
        )
    else:
        target = raw * kelly_fraction
        target = _apply_constraints(
            target, per_contract_cap, cluster_caps, cluster_assignments,
            default_cluster_cap, liquidity_caps, contract_ids, bankroll,
        )

    current_fractions = np.array([
        p["quantity"] * p["entry_price"] / bankroll for p in positions
    ])
    trades = target - current_fractions
    trades[np.abs(trades) < rebalance_threshold] = 0.0

    return KellyResult(
        target_fractions=target,
        raw_kelly=raw,
        recommended_trades=trades,
        contract_ids=contract_ids,
    )


def _optimize_joint_kelly(
    sim_returns, raw_kelly, kelly_mult, per_cap, cluster_caps,
    cluster_assignments, default_cluster_cap, liq_caps, ids, bankroll,
):
    """Joint optimization: maximize mean(log(1 + Σ f_i * r_i(s)))."""
    n = sim_returns.shape[1]
    initial = np.clip(raw_kelly * kelly_mult, -per_cap, per_cap)

    def neg_expected_log_wealth(f):
        portfolio_returns = sim_returns @ f
        wealth = 1.0 + portfolio_returns
        wealth = np.maximum(wealth, 1e-10)
        return -np.mean(np.log(wealth))

    bounds = [(-per_cap, per_cap) for _ in range(n)]

    if liq_caps:
        for i, cid in enumerate(ids):
            if cid in liq_caps:
                cap = liq_caps[cid] / bankroll
                bounds[i] = (max(bounds[i][0], -cap), min(bounds[i][1], cap))

    constraints = []
    if cluster_caps or cluster_assignments:
        clusters = {}
        if cluster_assignments:
            for i, cid in enumerate(ids):
                cl = cluster_assignments.get(cid, "default")
                clusters.setdefault(cl, []).append(i)
        for cl_name, indices in clusters.items():
            cap = (cluster_caps or {}).get(cl_name, default_cluster_cap)
            constraints.append({
                "type": "ineq",
                "fun": lambda f, idx=indices, c=cap: c - np.sum(np.abs(f[idx])),
            })

    result = minimize(
        neg_expected_log_wealth, initial, method="SLSQP",
        bounds=bounds, constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-10},
    )

    target = result.x if result.success else initial
    return _apply_constraints(
        target, per_cap, cluster_caps, cluster_assignments,
        default_cluster_cap, liq_caps, ids, bankroll,
    )


def _apply_constraints(
    target, per_cap, cluster_caps, cluster_assignments,
    default_cluster_cap, liq_caps, ids, bankroll,
):
    target = np.clip(target, -per_cap, per_cap)

    if liq_caps:
        for i, cid in enumerate(ids):
            if cid in liq_caps:
                cap = liq_caps[cid] / bankroll
                target[i] = np.clip(target[i], -cap, cap)

    if cluster_assignments:
        clusters = {}
        for i, cid in enumerate(ids):
            cl = cluster_assignments.get(cid, "default")
            clusters.setdefault(cl, []).append(i)
        for cl_name, indices in clusters.items():
            cap = (cluster_caps or {}).get(cl_name, default_cluster_cap)
            total = np.sum(np.abs(target[indices]))
            if total > cap:
                scale = cap / total
                target[indices] *= scale

    return target
