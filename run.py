#!/usr/bin/env python3
import sys
import os
import json
import numpy as np
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

MENU = """
=== kalsim Risk Desk ===

1) Pull live positions
2) Liquidity monitoring
3) Factor model
4) Dynamic correlation
5) VaR / CVaR
6) Kelly position sizing
7) Scenario stress testing
0) Quit
"""


def _check_credentials():
    if not os.environ.get("KALSHI_KEY_ID") or not os.environ.get("KALSHI_PRIVATE_KEY"):
        print("No Kalshi credentials found.")
        print("Set KALSHI_KEY_ID and KALSHI_PRIVATE_KEY in .env or environment.")
        return False
    return True


def get_live_positions():
    if not _check_credentials():
        return None, None
    from src.position_feed import PositionFeed
    feed = PositionFeed()
    positions = feed.get_positions()
    if not positions:
        print("No open positions.")
        return None, None
    return positions, feed.client


def _positions_as_dicts(positions):
    return [p.model_dump() for p in positions]


def run_positions():
    positions, _ = get_live_positions()
    if positions is None:
        return
    for p in positions:
        print(f"  {p.contract_id}: qty={p.quantity}, mid={p.current_mid:.2f}, "
              f"edge={p.edge:.3f}, tte={p.tte_days:.1f}d, "
              f"fee_be={p.fee_adjusted_breakeven:.3f}")


def run_liquidity():
    from src.liquidity import compute_liquidity_metrics

    positions, client = get_live_positions()
    if positions is None:
        return

    for p in positions:
        orderbook = client.get_orderbook(p.contract_id)
        m = compute_liquidity_metrics(
            p.contract_id, orderbook, quantity=p.quantity,
            entry_price=p.entry_price, tte_days=p.tte_days,
        )
        print(f"  {m.contract_id}: spread={m.spread_pct:.3f}, "
              f"slippage=${m.liquidation_slippage:.2f}, flag={m.liquidity_flag}")
        print(f"    depth bid={m.depth_at_best_bid}, depth ask={m.depth_at_best_ask}")


def _fetch_price_matrix(positions, client):
    all_series = []
    valid_ids = []
    for p in positions:
        history = client.get_market_history(p.contract_id)
        if not history:
            continue
        prices = []
        for snap in history:
            price = snap.get("yes_price", snap.get("close", snap.get("price")))
            if price is not None:
                if price > 1:
                    price = price / 100.0
                prices.append(price)
        if len(prices) >= 10:
            all_series.append(prices)
            valid_ids.append(p.contract_id)

    if len(valid_ids) < 2:
        print("Not enough price history (need at least 2 contracts with 10+ snapshots).")
        return None, None

    min_len = min(len(s) for s in all_series)
    matrix = np.column_stack([np.array(s[:min_len]) for s in all_series])
    return matrix, valid_ids


def run_factor_model():
    from src.factor_model import estimate_factor_model, reconstruct_covariance

    positions, client = get_live_positions()
    if positions is None:
        return

    prices, ids = _fetch_price_matrix(positions, client)
    if prices is None:
        return

    result = estimate_factor_model(prices, ids)
    print(f"  Factors: {result.n_factors}")
    print(f"  Explained variance: {result.explained_variance}")
    print(f"  Loadings shape: {result.loadings.shape}")

    cov = reconstruct_covariance(result)
    print(f"\n  Reconstructed covariance (diagonal): {np.diag(cov)}")


def run_correlation():
    from src.correlation import DynamicCorrelationModel, EventCalendar

    positions, client = get_live_positions()
    if positions is None:
        return

    prices, ids = _fetch_price_matrix(positions, client)
    if prices is None:
        return

    calendar = EventCalendar()
    model = DynamicCorrelationModel(calendar=calendar)
    model.fit_baseline(prices, window=min(90, prices.shape[0]))

    regime = model.get_current_correlation()
    print(f"  Regime: {regime.regime}")
    print(f"  Reason: {regime.reason}")
    print(f"  Matrix shape: {regime.matrix.shape}")
    print(f"  Correlation matrix diagonal: {np.diag(regime.matrix)}")


def run_var():
    from src.var_engine import simulate_pnl, run_dual_var

    positions, _ = get_live_positions()
    if positions is None:
        return

    pos_dicts = _positions_as_dicts(positions)
    corr = np.eye(len(pos_dicts))

    result = simulate_pnl(pos_dicts, corr, n_sims=50_000, seed=42)
    print(f"  VaR 95  = ${result.var_95:.2f}")
    print(f"  VaR 99  = ${result.var_99:.2f}")
    print(f"  CVaR 95 = ${result.cvar_95:.2f}")
    print(f"  P(ruin) = {result.p_ruin:.4f}")
    print(f"  Component VaR: {result.component_var}")

    model_r, market_r = run_dual_var(pos_dicts, corr, n_sims=50_000, seed=42)
    print(f"\n  Model  VaR95=${model_r.var_95:.2f}, CVaR95=${model_r.cvar_95:.2f}")
    print(f"  Market VaR95=${market_r.var_95:.2f}, CVaR95=${market_r.cvar_95:.2f}")


def run_kelly():
    from src.kelly import kelly_optimize

    positions, _ = get_live_positions()
    if positions is None:
        return

    pos_dicts = _positions_as_dicts(positions)
    result = kelly_optimize(pos_dicts, bankroll=10_000, kelly_fraction=0.25)
    for i, cid in enumerate(result.contract_ids):
        print(f"  {cid}: raw_kelly={result.raw_kelly[i]:.4f}, "
              f"target={result.target_fractions[i]:.4f}, "
              f"trade={result.recommended_trades[i]:.4f}")


def run_scenario():
    from src.scenario import Scenario, run_scenario_library, load_scenarios_from_json, Resolution

    positions, _ = get_live_positions()
    if positions is None:
        return

    pos_dicts = _positions_as_dicts(positions)

    scenarios_path = "scenarios.json"
    if not os.path.exists(scenarios_path):
        print(f"No {scenarios_path} found. Create it with scenario definitions to run stress tests.")
        print('Format: [{"name": "...", "world_state": {"key": "value"}, "description": "..."}]')
        return

    scenarios = load_scenarios_from_json(scenarios_path)
    if not scenarios:
        print("No scenarios defined in scenarios.json.")
        return

    resolution_rules = {}
    results = run_scenario_library(pos_dicts, scenarios, resolution_rules)
    print("  Scenarios:")
    for r in results:
        print(f"\n  '{r.scenario.name}': total P&L = ${r.pnl:.2f}")
        for cid, pnl in r.position_pnls.items():
            print(f"    {cid}: ${pnl:.2f}")


ACTIONS = {
    "1": ("Pull live positions", run_positions),
    "2": ("Liquidity monitoring", run_liquidity),
    "3": ("Factor model", run_factor_model),
    "4": ("Dynamic correlation", run_correlation),
    "5": ("VaR / CVaR", run_var),
    "6": ("Kelly position sizing", run_kelly),
    "7": ("Scenario stress testing", run_scenario),
}


def main():
    while True:
        print(MENU)
        choice = input("Select option: ").strip()
        if choice == "0":
            break
        if choice not in ACTIONS:
            print("Invalid option.")
            continue
        label, fn = ACTIONS[choice]
        print(f"\n--- {label} ---\n")
        try:
            fn()
        except Exception as e:
            print(f"Error: {e}")
        print()


if __name__ == "__main__":
    main()
