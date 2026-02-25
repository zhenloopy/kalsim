#!/usr/bin/env python3
"""CLI for kalsim risk desk — run scenarios from the README."""

import sys
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

def demo_positions():
    return [
        {"contract_id": "FED-HOLD", "quantity": 100, "entry_price": 0.55,
         "current_mid": 0.65, "model_prob": 0.70, "market_prob": 0.60},
        {"contract_id": "CPI-HIGH", "quantity": -50, "entry_price": 0.40,
         "current_mid": 0.35, "model_prob": 0.30, "market_prob": 0.35},
        {"contract_id": "GDP-POS", "quantity": 75, "entry_price": 0.50,
         "current_mid": 0.58, "model_prob": 0.62, "market_prob": 0.55},
    ]


def demo_prices(T=200, N=3):
    rng = np.random.default_rng(42)
    base = np.array([0.6, 0.35, 0.55])
    prices = np.empty((T, N))
    prices[0] = base
    for t in range(1, T):
        prices[t] = prices[t - 1] + rng.normal(0, 0.01, N)
    return np.clip(prices, 0.06, 0.94)


def demo_orderbook():
    return {
        "yes": [[65, 100], [60, 200], [55, 300]],
        "no": [[40, 120], [45, 250]],
    }


def run_positions():
    from src.position_feed import PositionFeed
    import os

    has_creds = os.environ.get("KALSHI_KEY_ID") and os.environ.get("KALSHI_PRIVATE_KEY")
    if not has_creds:
        print("No Kalshi credentials found in environment.")
        print("Set KALSHI_KEY_ID and KALSHI_PRIVATE_KEY to pull live data.")
        print("\nShowing demo position build instead:\n")
        from src.position_feed import build_position_from_data
        for p in demo_positions():
            pos = build_position_from_data(
                contract_id=p["contract_id"], platform="kalshi",
                canonical_event_id=p["contract_id"], quantity=p["quantity"],
                entry_price=p["entry_price"], current_mid=p["current_mid"],
                resolves_at=datetime.now(timezone.utc) + timedelta(days=30),
                fee_rate=0.07, model_prob=p["model_prob"],
            )
            print(f"  {pos.contract_id}: qty={pos.quantity}, mid={pos.current_mid:.2f}, "
                  f"edge={pos.edge:.3f}, tte={pos.tte_days:.1f}d, "
                  f"fee_be={pos.fee_adjusted_breakeven:.3f}")
        return

    feed = PositionFeed()
    positions = feed.get_positions()
    if not positions:
        print("No open positions found.")
        return
    for p in positions:
        print(f"  {p.contract_id}: qty={p.quantity}, mid={p.current_mid:.2f}, "
              f"edge={p.edge:.3f}, tte={p.tte_days:.1f}d, "
              f"fee_be={p.fee_adjusted_breakeven:.3f}")


def run_liquidity():
    from src.liquidity import compute_liquidity_metrics

    orderbook = demo_orderbook()
    print("Orderbook:", orderbook)
    for pos in demo_positions():
        m = compute_liquidity_metrics(
            pos["contract_id"], orderbook, quantity=pos["quantity"],
            entry_price=pos["entry_price"], tte_days=30.0,
        )
        print(f"\n  {m.contract_id}: spread={m.spread_pct:.3f}, "
              f"slippage=${m.liquidation_slippage:.2f}, flag={m.liquidity_flag}")
        print(f"    depth bid={m.depth_at_best_bid}, depth ask={m.depth_at_best_ask}")


def run_factor_model():
    from src.factor_model import estimate_factor_model, reconstruct_covariance

    prices = demo_prices(T=200, N=3)
    ids = [p["contract_id"] for p in demo_positions()]

    result = estimate_factor_model(prices, ids)
    print(f"  Factors: {result.n_factors}")
    print(f"  Explained variance: {result.explained_variance}")
    print(f"  Loadings shape: {result.loadings.shape}")

    cov = reconstruct_covariance(result)
    print(f"\n  Reconstructed covariance (diagonal): {np.diag(cov)}")


def run_correlation():
    from src.correlation import DynamicCorrelationModel, EventCalendar

    prices = demo_prices(T=200, N=3)

    calendar = EventCalendar()
    calendar.add_event("FOMC", datetime(2026, 3, 19, 18, 0, tzinfo=timezone.utc), "FOMC March")

    model = DynamicCorrelationModel(calendar=calendar)
    model.fit_baseline(prices, window=90)

    regime = model.get_current_correlation()
    print(f"  Regime: {regime.regime}")
    print(f"  Reason: {regime.reason}")
    print(f"  Matrix shape: {regime.matrix.shape}")
    print(f"  Correlation matrix diagonal: {np.diag(regime.matrix)}")


def run_var():
    from src.var_engine import simulate_pnl, run_dual_var

    positions = demo_positions()
    corr = np.eye(len(positions))

    result = simulate_pnl(positions, corr, n_sims=50_000, seed=42)
    print(f"  VaR 95  = ${result.var_95:.2f}")
    print(f"  VaR 99  = ${result.var_99:.2f}")
    print(f"  CVaR 95 = ${result.cvar_95:.2f}")
    print(f"  P(ruin) = {result.p_ruin:.4f}")
    print(f"  Component VaR: {result.component_var}")

    model_r, market_r = run_dual_var(positions, corr, n_sims=50_000, seed=42)
    print(f"\n  Model  VaR95=${model_r.var_95:.2f}, CVaR95=${model_r.cvar_95:.2f}")
    print(f"  Market VaR95=${market_r.var_95:.2f}, CVaR95=${market_r.cvar_95:.2f}")


def run_kelly():
    from src.kelly import kelly_optimize

    positions = demo_positions()
    result = kelly_optimize(
        positions, bankroll=10_000, kelly_fraction=0.25,
        per_contract_cap=0.05, liquidity_caps={"FED-HOLD": 500.0},
    )
    for i, cid in enumerate(result.contract_ids):
        print(f"  {cid}: raw_kelly={result.raw_kelly[i]:.4f}, "
              f"target={result.target_fractions[i]:.4f}, "
              f"trade={result.recommended_trades[i]:.4f}")


def run_scenario():
    from src.scenario import Scenario, compute_scenario_pnl, run_scenario_library, Resolution

    positions = demo_positions()

    resolution_rules = {
        "FED-HOLD": lambda ws: Resolution.YES if ws.get("fed") == "hold" else Resolution.NO,
        "CPI-HIGH": lambda ws: Resolution.YES if ws.get("cpi") == ">3%" else Resolution.NO,
        "GDP-POS":  lambda ws: Resolution.YES if ws.get("gdp") == "positive" else Resolution.NO,
    }

    scenarios = [
        Scenario("Fed holds, low CPI, GDP growth",
                 {"fed": "hold", "cpi": "<3%", "gdp": "positive"},
                 "Goldilocks scenario"),
        Scenario("Fed hikes, CPI spike",
                 {"fed": "hike", "cpi": ">3%", "gdp": "negative"},
                 "Stagflation scenario"),
        Scenario("Fed holds, CPI spike, GDP flat",
                 {"fed": "hold", "cpi": ">3%", "gdp": "flat"},
                 "Mixed scenario"),
    ]

    print("  Scenarios:")
    results = run_scenario_library(positions, scenarios, resolution_rules)
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
