# WebSocket + TUI Refactor Design

## Goals
1. Replace REST polling with persistent websocket for orderbook/price state
2. Fetch positions once at startup, update via fill channel
3. Build a Textual-based TUI with live-updating trading terminal feel
4. Handle signals (Ctrl+C), resize, unexpected input seamlessly

## WebSocket Architecture

### Connection
- URL: `wss://api.elections.kalshi.com/trade-api/ws/v2`
- Auth: RSA-PSS signature in headers (same as REST)
- Signature message: `{timestamp}GET/trade-api/ws/v2`

### Channels
| Channel | Auth | Purpose |
|---------|------|---------|
| `orderbook_delta` | yes | Snapshot + incremental orderbook updates |
| `ticker` | no | Price/volume/OI changes |
| `fill` | yes | Our trade fills (position updates) |

### Message Flow
1. Connect with auth headers
2. Subscribe to `orderbook_delta` with `market_tickers` for held contracts
3. Subscribe to `ticker` for same contracts
4. Subscribe to `fill` for our fills
5. Process: snapshot → apply deltas → update BookState

### Orderbook Delta Protocol
- First message: `orderbook_snapshot` with full `yes`/`no` arrays (price in cents, qty)
- Subsequent: `orderbook_delta` with `{price, delta, side}` — delta is signed qty change
- Apply delta to local state: `book[side][price] += delta`, remove if qty <= 0

## BookState (Shared In-Memory State)

Single source of truth for all live market data:
- `positions`: list of Position objects (init from REST, updated via fills)
- `orderbooks`: dict of ticker → {yes: {price: qty}, no: {price: qty}}
- `ticker_data`: dict of ticker → {last_price, volume, open_interest}
- Asyncio-safe (single event loop, no threading needed with Textual)

## TUI Design (Textual)

### Layout
```
Header: app name, ws status indicator, clock
Body: Left 70% = main content, Right 30% = risk sidebar
Footer: tab bar + keybindings help
```

### Tabs (main content area)
1. **Positions** — live table of all positions with mid/edge/PnL
2. **Orderbook** — live orderbook for selected contract
3. **VaR/Risk** — full VaR/CVaR details + component VaR
4. **Kelly** — optimal sizing + recommended trades
5. **Scenarios** — stress test results
6. **Liquidity** — liquidity metrics per contract

### Risk Sidebar (always visible)
- Portfolio VaR 95/99
- CVaR 95
- P(ruin)
- Total PnL
- Top liquidity flags

### Keybindings
- `1-6`: switch tabs
- `j/k` or `↑/↓`: navigate rows
- `r`: force refresh (re-run computations)
- `q`: quit (graceful shutdown)
- `Ctrl+C`: same as q

### Performance Considerations
- Orderbook updates are O(1) dict operations
- Risk computations (VaR, Kelly) run in background workers, not on UI thread
- DataTable updates only changed cells, not full re-render
- Debounce rapid orderbook updates (batch within 100ms for UI refresh)

## Module Changes

| Module | Action |
|--------|--------|
| `src/ws_client.py` | NEW — async websocket client |
| `src/book_state.py` | NEW — shared state management |
| `src/tui/app.py` | NEW — main Textual app |
| `src/tui/screens.py` | NEW — tab screen definitions |
| `src/tui/widgets.py` | NEW — custom widgets (orderbook, risk sidebar) |
| `src/tui/styles.css` | NEW — Textual CSS styling |
| `src/kalshi_client.py` | KEEP — initial REST calls |
| `src/position_feed.py` | REFACTOR — read from BookState |
| `src/liquidity.py` | MINOR — accept orderbook dict input |
| `run.py` | REPLACE — launch TUI app |

## Dependencies Added
- `textual` — TUI framework
- `websockets` — async websocket client
