Feature 1 — VaR / CVaR Engine
What it is. A Monte Carlo simulation that produces a portfolio-level loss distribution and extracts standard risk metrics.
How it works:

Draw 10,000 correlated standard normal vectors using the current correlation matrix (from Feature 4)
Apply probability integral transform: U_i = Φ(Z_i)
Each contract resolves YES in simulation s if U_i,s < model_prob_i
Compute portfolio P&L per simulation; add liquidation slippage (from Feature 5) in tail scenarios
Output: VaR_95, VaR_99, CVaR_95, P(ruin), component VaR per position

Run twice: once with model_prob, once with market_prob. The gap between the two distributions shows how much your beliefs diverge from consensus.
What it feeds. Feature 7 (baseline loss distribution for scenario comparison), dashboard display.
How to test. Run against a single-contract portfolio; assert VaR equals full position size when market_prob > 0.95; assert two independent portfolios have VaR ≤ sum of individual VaRs (subadditivity of CVaR).

Feature 8 — Kelly Optimizer
What it is. A convex optimizer that computes target position sizes maximizing expected log wealth, subject to liquidity and concentration constraints.
How it works:

For each contract with edge > min_edge (e.g., 3 cents after fees), compute raw Kelly fraction: f* = (model_prob - market_prob) / (1 - market_prob)
Scale by fractional Kelly multiplier λ (0.25 default; up to 0.50 for high-conviction positions)
Solve multi-contract joint optimization using the simulations from Feature 1 as the probability measure: maximize mean(log(1 + Σ_i f_i · r_i(s))) over simulations
Apply constraints: per-contract cap (5% of bankroll), factor-cluster cap (15% per cluster from Feature 2), liquidity cap (from Feature 5)
Output: target allocation vector; recommended trade = target - current; suppress trades below rebalancing threshold

What it feeds. Trade recommendations, dashboard display.
How to test. Single-contract case: assert optimizer recovers analytical Kelly fraction; assert that setting all edges to zero produces zero allocations; assert no recommended position exceeds its liquidity cap.

Feature 7 — Scenario Engine
What it is. An offline stress tester that evaluates portfolio P&L under constructed world states and compares against statistical VaR.
How it works:

Define scenarios as partial or complete assignments of real-world outcomes (e.g., {fed_march: "hold", cpi_feb: ">3%"})
For each open contract, a resolution function maps the world state to YES / NO / INDETERMINATE; indeterminate contracts retain current market price
Compute deterministic P&L for each scenario
Store scenarios in a YAML/JSON library; run full library daily; flag any scenario where loss > VaR_99

Scenarios where loss >> VaR_99 identify tail risks the statistical model is missing.
What it feeds. Human review, model validation.
How to test. Construct a scenario that resolves all held positions against you; assert P&L equals maximum possible loss; assert that a scenario with no overlap with current positions produces zero P&L impact.
