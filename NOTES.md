# Risk Desk — Architecture Notes

## Project Structure
```
src/
  config.py          - Configuration (API credentials, fee rates)
  schema.py          - Pydantic Position model (canonical schema)
  kalshi_client.py   - Kalshi REST API client
  position_feed.py   - Normalizes raw Kalshi data → Position schema
tests/
  test_position_feed.py - Fee math, schema validation, mid computation
```

## Feature Status
- [x] Feature 6 — Unified Position Feed
- [ ] Feature 5 — Liquidity Monitor
- [ ] Feature 2 — Factor Model
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

### Dependency Order
Feature 6 → {Feature 5, Feature 2} → Feature 4 → Feature 1 → {Feature 7, Feature 8}
