# Risk Desk — Architecture Notes

## Project Structure
```
src/
  config.py          - Configuration (API credentials, fee rates)
  schema.py          - Pydantic Position model (canonical schema)
  kalshi_client.py   - Kalshi REST API client (used for initial fetch)
  ws_client.py       - Async websocket client for live streaming
  book_state.py      - Shared in-memory state (positions, orderbooks, tickers)
  collector.py       - Background NAV collector (detached process, CLI + importable)
  position_feed.py   - Normalizes raw Kalshi data → Position schema
  liquidity.py       - Per-position liquidity metrics from order book
  factor_model.py    - PCA factor decomposition with Ledoit-Wolf shrinkage
  correlation.py     - Dynamic correlation with event-driven regime switching
  var_engine.py      - Monte Carlo VaR/CVaR with correlated binary resolution
  kelly.py           - Kelly criterion optimizer with constraints
  scenario.py        - Scenario stress testing with deterministic P&L
  tui/
    app.py           - Main Textual TUI application
    widgets.py       - Custom widgets (OrderbookDisplay, CachedDataTable, ScenarioInput, SettingsPanel)
    styles.tcss      - Textual CSS styling
tests/
  test_position_feed.py - Fee math, schema validation, mid computation
  test_liquidity.py     - Slippage hand calculations, flag thresholds
  test_factor_model.py  - Covariance reconstruction, stability across windows
  test_correlation.py   - Regime switching, pre-event vs baseline correlation
  test_var_engine.py    - Single-contract VaR, CVaR subadditivity, slippage
  test_kelly.py         - Analytical Kelly recovery, constraints, cluster caps
  test_scenario.py      - Worst case P&L, no-overlap zero impact, JSON loading
  test_book_state.py    - Orderbook delta application, PnL, mid price updates
  test_ws_client.py     - WS message parsing, BookState integration
  test_collector.py     - PID management, process lifecycle, stale PID detection
```

## Feature Status
- [x] Feature 6 — Unified Position Feed
- [x] Feature 5 — Liquidity Monitor
- [x] Feature 2 — Factor Model
- [x] Feature 4 — Dynamic Correlation Model
- [x] Feature 1 — VaR / CVaR Engine
- [x] Feature 8 — Kelly Optimizer
- [x] Feature 7 — Scenario Engine
- [x] WebSocket Integration
- [x] TUI (Textual-based terminal UI)
- [x] Background NAV Collector

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

## Implemented: Feature 4 — Dynamic Correlation Model

**Pre-event window stitching.** When collecting historical pre-event windows, logit-returns are computed WITHIN each window before concatenation. This avoids artificial jumps at window boundaries that would corrupt the covariance estimate.

**Regime switching.** Event calendar checked for events within configurable hours (default 72h). First matching event type with a fitted pre-event matrix triggers the switch. Falls back to baseline otherwise. All switches are logged with reason.

## Implemented: Feature 1 — VaR / CVaR Engine

**Simulation approach.** Draw correlated standard normals via Cholesky, apply Φ(Z) → U ~ Uniform, resolve YES if U < prob. P&L computed from entry price and quantity. Fallback to eigenvalue decomposition if Cholesky fails (non-PD matrix).

**Dual run.** `run_dual_var` produces two VaR results (model_prob vs market_prob) to quantify belief divergence.

**Slippage add-on.** In tail scenarios (worst `slippage_tail_pct` fraction), total liquidation slippage is subtracted from P&L.

**Component VaR.** Marginal contribution computed as average per-position loss in the VaR tail scenarios.

## Implemented: Feature 8 — Kelly Optimizer

**Two-path optimization.** Analytical Kelly (fractional scaling of `f* = (p-q)/(1-q)`) when no simulation data available. Joint log-wealth maximization via SLSQP when simulated returns are provided.

**Constraint layering.** Applied in order: per-contract cap (default 5%), liquidity cap (per-contract dollar limit), cluster cap (15% per factor cluster). Constraints are enforced both in the optimizer bounds and as a post-optimization clamp.

**Edge gating.** Contracts with |edge| < min_edge (default 3c) get zero allocation regardless of other factors.

## Implemented: Feature 7 — Scenario Engine

**Three-state resolution.** Each contract resolves YES, NO, or INDETERMINATE per scenario. Indeterminate contracts use current mid price (mark-to-market), not entry price.

**Resolution rules as callables.** Rules are `{contract_id: Callable(world_state) → Resolution}`, allowing arbitrary logic per contract. Missing rules default to INDETERMINATE.

**VaR_99 flagging.** Scenarios where loss exceeds VaR_99 are automatically flagged, identifying tail risks the statistical model misses.

**Extended scenario format.** Two new optional fields on `Scenario`:
- `resolution_overrides: {contract_id: "YES"|"NO"}` — force specific contracts to resolve deterministically
- `probability_overrides: {contract_id: float}` — expected value P&L at a user-modeled probability (`pnl = qty * (prob - entry)`)

**Override priority chain.** When computing scenario P&L: probability_overrides → resolution_overrides → resolution_rules (callables) → INDETERMINATE (mark-to-market). A contract can only appear in one override dict (validated).

**TUI scenario input.** `ScenarioInput` widget at the top of the Scenarios tab: TextArea with JSON template, inline validation errors, Submit button below. Valid scenarios are appended to `scenarios.json` and the results panel refreshes immediately.

**Validation.** `validate_scenario_json(raw)` parses and validates all fields with clear error messages: required name/world_state, optional description, resolution values must be "YES"/"NO", probability values must be floats in [0,1], no contract can appear in both override dicts.

### Dependency Order (all complete)
Feature 6 → {Feature 5, Feature 2} → Feature 4 → Feature 1 → {Feature 7, Feature 8}

## Implemented: WebSocket Integration

**Connection.** Single persistent websocket to `wss://api.elections.kalshi.com/trade-api/ws/v2` with RSA-PSS auth headers (same signing as REST). Auto-reconnect with exponential backoff (1s → 30s max).

**Channels.** Three subscriptions:
- `orderbook_delta` (private) — snapshot followed by incremental deltas per contract
- `ticker` (public) — price/volume/OI changes
- `fill` (private) — our trade fills for position tracking

**BookState.** Central in-memory state object. Orderbooks stored as `{side: {price_cents: qty}}` dicts for O(1) delta application. Converted to sorted API-compatible format on read. Position mids recomputed automatically on every orderbook update.

**Startup flow.** Positions and orderbooks fetched via REST once at startup (reliable, complete). Websocket connects after, subscribing to all held tickers. Future updates arrive via WS, keeping state fresh without polling.

## Implemented: NAV Display + Historical Chart

**NAV computation.** `BookState.compute_nav()` = `cash_balance + Σ(qty × current_mid)`. Uses live mid prices from websocket-updated orderbooks rather than the static `portfolio_value` from REST. Displayed in the header subtitle bar.

**Persistence.** `NavStore` in `src/nav_store.py` — SQLite (stdlib `sqlite3`) with WAL mode, stored at `data/nav.db`. Records NAV snapshots every 60 seconds plus once at startup. Schema: `nav_snapshots(timestamp_utc, nav, cash, portfolio_value, unrealized_pnl, position_count)`.

**Chart.** `NavChart` widget in the Positions tab using `textual-plotext`. Time range selector buttons (1H through 5Y, default 1W). Queries up to 500 points per range with bucket-average downsampling when data exceeds that. Auto-refreshes every 60s with the recording timer and on manual `r` key refresh.

**Data retention.** No automatic pruning — SQLite file grows unbounded. At one row per minute that's ~500KB/year, negligible.

## Implemented: Background NAV Collector

**Problem.** NAV snapshots only recorded while the TUI is running. Gaps in data whenever the app is closed.

**Solution.** `src/collector.py` — a detached OS process that polls Kalshi REST every 60s, computes NAV, and writes to the same `data/nav.db` SQLite. Survives TUI exit.

**Process management.** PID file at `data/collector.pid`. Cross-platform: `start_new_session=True` on Unix, `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` on Windows. `stop` sends SIGTERM (Unix) or TerminateProcess (Windows). Stale PID files detected and cleaned automatically.

**CLI.** `python -m src.collector start|stop|status [--interval 60]`

**TUI integration.** Settings tab (tab 8) provides collector controls: ON/OFF toggle buttons and interval selector (1m, 5m, 30m, 1hr, 24hr). Changing interval while running auto-restarts the collector. `c` keybinding also toggles collector on/off. Status shown in subtitle bar (`Collector:ON/OFF`). Calls importable `start_collector()` / `stop_collector()` / `collector_status()` functions.

**Why REST not WS?** For 1-minute snapshots, a single `get_positions()` + `get_balance()` REST cycle is simpler and sufficient. WS requires async machinery and persistent connections.

**PID cleanup safety.** Child's atexit handler checks that PID file still contains its own PID before deleting, preventing a race where stop→start→old atexit would remove the new process's PID file.

## Implemented: TUI (Textual)

**Framework.** Textual 8.x — async Python TUI framework. Single event loop manages both websocket and UI rendering.

**Layout.** Header (title + clock + subtitle with position count/PnL/WS status) → full-width tabbed content → footer (keybindings).

**Tabs.** 8 views: Positions, Orderbook, VaR/Risk, Kelly, Scenarios, Liquidity, Docs, Settings. Switchable via number keys 1-8.

**Performance.** UI updates debounced at 150ms to prevent rapid WS deltas from flooding the renderer. Risk computations (VaR Monte Carlo, Kelly optimization, liquidity metrics) run in Textual thread workers, not on the UI thread. Recomputed every 10s or on manual refresh (r key).

**Bankroll.** Kelly optimizer uses live account bankroll (cash_balance + portfolio_value) fetched from `GET /portfolio/balance` at startup, instead of a hardcoded value.

**Docs tab.** Built-in documentation accessible via tab 7. Covers all columns, formulas, and flag thresholds.

**Signal handling.** Ctrl+C and q both trigger graceful shutdown (WS disconnect, app exit). Escape deselects. Unknown keys are ignored by Textual's event system.
