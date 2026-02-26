# kalsim — Prediction Market Risk Desk

Risk analytics for Kalshi prediction market portfolios. Computes VaR/CVaR, liquidity metrics, factor decomposition, optimal position sizing, and scenario stress tests.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Set environment variables for Kalshi API access (or add to `.env`):

```bash
export KALSHI_KEY_ID="your-key-id"
export KALSHI_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"

# optional
export KALSHI_FEE_RATE="0.07"  # default 7%
export KALSHI_API_URL="https://api.elections.kalshi.com/trade-api/v2"
```

## Usage

### Pull live positions

```python
from src.position_feed import PositionFeed

feed = PositionFeed()
positions = feed.get_positions()
for p in positions:
    print(f"{p.contract_id}: qty={p.quantity}, mid={p.current_mid:.2f}, "
          f"edge={p.edge:.3f}, tte={p.tte_days:.1f}d, flag_be={p.fee_adjusted_breakeven:.3f}")
```

You can inject your own probability estimates:

```python
feed = PositionFeed(model_probs={"TICKER-YES": 0.72})
```

### Liquidity monitoring

```python
from src.liquidity import compute_liquidity_metrics

# orderbook format: {"yes": [[price_cents, qty], ...], "no": [[price_cents, qty], ...]}
orderbook = {"yes": [[55, 100], [50, 200]], "no": [[40, 150]]}
metrics = compute_liquidity_metrics(
    "TICKER-YES", orderbook, quantity=50, entry_price=0.52, tte_days=10.0
)
print(f"spread={metrics.spread_pct:.3f}, slippage=${metrics.liquidation_slippage:.2f}, "
      f"flag={metrics.liquidity_flag}")
```

### Factor model

```python
import numpy as np
from src.factor_model import estimate_factor_model

# daily_prices: (T, N) array of contract prices in [0, 1]
daily_prices = np.random.uniform(0.2, 0.8, (200, 6))
contract_ids = ["A", "B", "C", "D", "E", "F"]

result = estimate_factor_model(daily_prices, contract_ids)
print(f"Factors: {result.n_factors}, explained: {result.explained_variance}")
print(f"Loadings shape: {result.loadings.shape}")
```

### Dynamic correlation

```python
from datetime import datetime, timezone, timedelta
from src.correlation import DynamicCorrelationModel, EventCalendar

calendar = EventCalendar()
calendar.add_event("FOMC", datetime(2026, 3, 19, 18, 0, tzinfo=timezone.utc), "FOMC March")

model = DynamicCorrelationModel(calendar=calendar)
model.fit_baseline(daily_prices, window=90)

regime = model.get_current_correlation()
print(f"Regime: {regime.regime}, reason: {regime.reason}")
# regime.matrix is the current correlation/covariance matrix
```

### VaR / CVaR

```python
from src.var_engine import simulate_pnl, run_dual_var
import numpy as np

positions = [
    {"quantity": 100, "entry_price": 0.55, "model_prob": 0.65, "market_prob": 0.60},
    {"quantity": -50, "entry_price": 0.40, "model_prob": 0.35, "market_prob": 0.40},
]
corr = np.eye(2)  # or use correlation model output

result = simulate_pnl(positions, corr, n_sims=10_000, seed=42)
print(f"VaR95=${result.var_95:.2f}, VaR99=${result.var_99:.2f}, "
      f"CVaR95=${result.cvar_95:.2f}, P(ruin)={result.p_ruin:.4f}")

# compare model beliefs vs market consensus
model_r, market_r = run_dual_var(positions, corr)
print(f"Model VaR95=${model_r.var_95:.2f}, Market VaR95=${market_r.var_95:.2f}")
```

### Kelly position sizing

```python
from src.kelly import kelly_optimize

positions = [
    {"contract_id": "A", "model_prob": 0.70, "market_prob": 0.55,
     "quantity": 10, "entry_price": 0.55},
]

result = kelly_optimize(
    positions, bankroll=10_000, kelly_fraction=0.25,
    per_contract_cap=0.05, liquidity_caps={"A": 500.0},
)
print(f"Target fraction: {result.target_fractions}")
print(f"Recommended trades: {result.recommended_trades}")
```

### Scenario stress testing

```python
from src.scenario import Scenario, compute_scenario_pnl, Resolution, load_scenarios_from_json

positions = [
    {"contract_id": "FED-HOLD", "quantity": 100, "entry_price": 0.60, "current_mid": 0.65},
]

resolution_rules = {
    "FED-HOLD": lambda ws: Resolution.YES if ws.get("fed") == "hold" else Resolution.NO,
}

scenario = Scenario("Fed holds", {"fed": "hold"})
result = compute_scenario_pnl(positions, scenario, resolution_rules)
print(f"Scenario '{result.scenario.name}': P&L = ${result.pnl:.2f}")

# or load from JSON file
scenarios = load_scenarios_from_json("scenarios.json")
```

Scenario JSON format:

```json
[
  {"name": "Fed holds rates", "world_state": {"fed": "hold"}, "description": "..."},
  {"name": "CPI spike", "world_state": {"cpi": ">3%"}}
]
```

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

104 tests covering fee math identities, slippage hand calculations, covariance reconstruction, CVaR subadditivity, Kelly analytical recovery, and scenario P&L bounds.

## Architecture

```
src/
  config.py          Configuration (API credentials, fee rates)
  schema.py          Canonical Position model (Pydantic)
  kalshi_client.py   Kalshi REST API client
  position_feed.py   Normalizes Kalshi data -> Position schema
  liquidity.py       Spread, depth, Amihud, slippage, liquidity flags
  factor_model.py    PCA factor decomposition (Ledoit-Wolf shrinkage)
  correlation.py     Event-driven regime-switching correlation
  var_engine.py      Monte Carlo VaR/CVaR (Gaussian copula)
  kelly.py           Kelly criterion optimizer with constraints
  scenario.py        Deterministic scenario stress testing
```

See `NOTES.md` for detailed architectural decisions.
