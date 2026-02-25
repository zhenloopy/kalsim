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
