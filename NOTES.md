# Risk Desk — Architecture Notes

## Project Structure
```
src/
  config.py          - Configuration (API credentials, fee rates)
  schema.py          - Pydantic Position model (canonical schema)
  kalshi_client.py   - Kalshi REST API client
  position_feed.py   - Normalizes raw Kalshi data → Position schema
  liquidity.py       - Per-position liquidity metrics from order book
  factor_model.py    - PCA factor decomposition with Ledoit-Wolf shrinkage
tests/
  test_position_feed.py - Fee math, schema validation, mid computation
  test_liquidity.py     - Slippage hand calculations, flag thresholds
  test_factor_model.py  - Covariance reconstruction, stability across windows
```

## Feature Status
- [x] Feature 6 — Unified Position Feed
- [x] Feature 5 — Liquidity Monitor
- [x] Feature 2 — Factor Model
- [ ] Feature 4 — Dynamic Correlation Model
- [ ] Feature 1 — VaR / CVaR Engine
- [ ] Feature 8 — Kelly Optimizer
- [ ] Feature 7 — Scenario Engine

## Implemented: Feature 6 — Unified Position Feed

### Key Decisions

**Fee-adjusted breakeven math.** For a long YES position at mid price m with fee rate f:
```
breakeven_prob = m / [m + (1-m)(1-f)]
```
This is the probability at which expected value equals zero after fees. For short positions the formula is symmetric. Verified by direct zero-EV identity tests.

**market_prob = current_mid.** On prediction markets the mid price IS the implied probability. The fee_adjusted_breakeven captures how fees shift the breakeven away from the raw mid.

**Orderbook mid computation.** Best YES bid and best NO bid (converted to YES ask) are averaged. Falls back to single-side price or last traded price when book is thin.

**canonical_event_id.** Uses Kalshi's `event_ticker` field to group contracts belonging to the same underlying event. This is the hook for cross-platform matching when Polymarket is added.

## Implemented: Feature 5 — Liquidity Monitor

**Slippage estimation.** Walks the order book level by level to compute VWAP of a full position exit. Slippage = |mid - vwap| × quantity. Unfilled quantity beyond book depth assumes worst-case fill (0 for sells, 1 for buys).

**Crossed-book guard.** If YES bid ≥ YES ask (impossible in a real market but can appear in stale data), ask is clamped to bid + 1c to avoid negative spreads.

**Flag thresholds.** CRITICAL if tte < 3 days. WATCH if tte < 14 days OR spread > 5%. Otherwise NORMAL. Boundary: tte=3 exactly is WATCH, not CRITICAL.

## Implemented: Feature 2 — Factor Model

**Logit transform.** Prices → log-odds before computing returns, linearizing the probability space. Extreme prices (< 5% or > 95%) filtered out since logit is unstable near 0/1.

**Ledoit-Wolf shrinkage.** Applied to the covariance of logit-return changes (not raw returns) to get a well-conditioned estimate. PCA runs on this shrunk covariance.

**Reconstruction identity.** By construction: B·Σ_F·B' + diag(Σ_ε) reconstructs the shrunk covariance matrix exactly on the diagonal. Off-diagonal error is bounded by the idiosyncratic components dropped by PCA.

**Auto factor count.** Scree-based: keep adding factors (2–4) until cumulative explained variance exceeds 50%.

### Dependency Order
Feature 6 → {Feature 5, Feature 2} → Feature 4 → Feature 1 → {Feature 7, Feature 8}
