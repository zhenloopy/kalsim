import asyncio
import time
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Header, Footer, Static, DataTable, Label, TabbedContent, TabPane, Tabs,
)
from textual.worker import Worker, WorkerState

from src.book_state import BookState
from src.tui.widgets import OrderbookDisplay, CachedDataTable, ScenarioInput
from src.tui.nav import PageNavMixin, NAV_BINDINGS

CSS_PATH = Path(__file__).parent / "styles.tcss"

UI_DEBOUNCE_MS = 150


class BookUpdated(Message):
    pass


class RiskDeskApp(PageNavMixin, App):
    """kalsim Risk Desk — TUI for prediction market portfolio management."""

    TITLE = "kalsim Risk Desk"
    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("1", "tab('positions')", "1:Pos", show=True),
        Binding("2", "tab('orderbook')", "2:Book", show=True),
        Binding("3", "tab('var')", "3:VaR", show=True),
        Binding("4", "tab('kelly')", "4:Kelly", show=True),
        Binding("5", "tab('scenarios')", "5:Scen", show=True),
        Binding("6", "tab('liquidity')", "6:Liq", show=True),
        Binding("7", "tab('docs')", "7:Docs", show=True),
        Binding("escape", "focus_tabs", "Nav", show=False),
        *NAV_BINDINGS,
    ]

    def __init__(self, book_state: BookState, **kwargs):
        super().__init__(**kwargs)
        self.book_state = book_state
        self._selected_ticker: str | None = None
        self._var_result = None
        self._kelly_result = None
        self._liquidity_metrics = []
        self._update_timer = None
        self._risk_worker: Worker | None = None
        self._last_ui_update = 0.0
        self._debounce_pending = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="content-area"):
            with TabPane("Positions", id="positions"):
                yield CachedDataTable(id="positions-table")
            with TabPane("Orderbook", id="orderbook"):
                yield CachedDataTable(id="ob-positions-table")
                yield OrderbookDisplay()
            with TabPane("VaR/Risk", id="var"):
                yield VerticalScroll(Static(id="var-content"), id="var-panel")
            with TabPane("Kelly", id="kelly"):
                yield VerticalScroll(Static(id="kelly-content"), id="kelly-panel")
            with TabPane("Scenarios", id="scenarios"):
                yield ScenarioInput(id="scenario-input")
                yield VerticalScroll(Static(id="scenario-content"), id="scenario-panel")
            with TabPane("Liquidity", id="liquidity"):
                yield CachedDataTable(id="liquidity-table")
            with TabPane("Docs", id="docs"):
                yield VerticalScroll(Static(id="docs-content"), id="docs-panel")
        yield Footer()

    def on_mount(self):
        table = self.query_one("#positions-table", CachedDataTable)
        table.add_columns("Contract", "Qty", "Entry", "Mid", "Edge", "PnL", "TTE", "Flag")
        table.cursor_type = "row"

        ob_table = self.query_one("#ob-positions-table", CachedDataTable)
        ob_table.add_columns("Contract", "Qty", "Mid")
        ob_table.cursor_type = "row"

        liq_table = self.query_one("#liquidity-table", CachedDataTable)
        liq_table.add_columns("Contract", "Spread%", "BidDepth", "AskDepth", "Slippage", "Flag")
        liq_table.cursor_type = "row"

        try:
            tabs_widget = self.query_one(Tabs)
            _orig = tabs_widget._highlight_active
            def _no_anim(animate=True):
                _orig(animate=False)
            tabs_widget._highlight_active = _no_anim
        except Exception:
            pass

        self.book_state.on_change(lambda: self.post_message(BookUpdated()))

        self._refresh_positions_table()
        self._refresh_ob_positions_table()
        self._refresh_docs_panel()
        self._update_subtitle()

        self._update_timer = self.set_interval(2.0, self._periodic_refresh)
        self.set_interval(10.0, self._run_risk_computations)

        if self.book_state.positions:
            self._run_risk_computations()

    def on_book_updated(self, event: BookUpdated):
        """Handles BookState changes routed through Textual's message queue."""
        now = time.monotonic()
        if now - self._last_ui_update < UI_DEBOUNCE_MS / 1000.0:
            if not self._debounce_pending:
                self._debounce_pending = True
                self.set_timer(UI_DEBOUNCE_MS / 1000.0, self._flush_debounced)
            return
        self._last_ui_update = now
        self._on_book_update()

    def _flush_debounced(self):
        self._debounce_pending = False
        self._last_ui_update = time.monotonic()
        self._on_book_update()

    def _on_book_update(self):
        self._refresh_positions_table()
        self._refresh_ob_positions_table()
        self._refresh_orderbook()
        self._update_subtitle()

    def _update_subtitle(self):
        n = len(self.book_state.positions)
        ws = "WS:ON" if self.book_state.ws_connected else "WS:OFF"
        pnl = self.book_state.get_total_pnl()
        self.sub_title = f"{n} positions | PnL: ${pnl:+.2f} | {ws}"

    def _periodic_refresh(self):
        self._refresh_positions_table()
        self._refresh_ob_positions_table()
        self._update_subtitle()

    def _refresh_positions_table(self):
        rows, keys = [], []
        cash = self.book_state.cash_balance
        rows.append(("$CASH", "", f"${cash:,.2f}", "", "", "", "", ""))
        keys.append("$CASH")
        for pos in self.book_state.positions:
            pnl = self.book_state.get_position_pnl(pos)
            flag = self._get_flag_for(pos.contract_id)
            is_short = pos.quantity < 0
            display_entry = (1.0 - pos.entry_price) if is_short else pos.entry_price
            display_mid = (1.0 - pos.current_mid) if is_short else pos.current_mid
            rows.append((
                pos.contract_id, str(pos.quantity),
                f"{display_entry:.2f}", f"{display_mid:.2f}",
                f"{pos.edge:+.3f}", f"${pnl:+.2f}",
                f"{pos.tte_days:.1f}d", flag,
            ))
            keys.append(pos.contract_id)
        self.query_one("#positions-table", CachedDataTable).update_rows(rows, keys)

    def _refresh_ob_positions_table(self):
        rows, keys = [], []
        for pos in self.book_state.positions:
            is_short = pos.quantity < 0
            display_mid = (1.0 - pos.current_mid) if is_short else pos.current_mid
            rows.append((pos.contract_id, str(pos.quantity), f"{display_mid:.2f}"))
            keys.append(pos.contract_id)
        self.query_one("#ob-positions-table", CachedDataTable).update_rows(rows, keys)

    def _get_flag_for(self, contract_id: str) -> str:
        for m in self._liquidity_metrics:
            if m.contract_id == contract_id:
                return m.liquidity_flag
        return "-"

    def _refresh_orderbook(self):
        if self._selected_ticker is None:
            return
        ob_display = self.query_one(OrderbookDisplay)
        ob = self.book_state.get_orderbook_for_api(self._selected_ticker)
        ob_display.update_orderbook(self._selected_ticker, ob)

    def _refresh_var_panel(self):
        content = self.query_one("#var-content", Static)
        if self._var_result is None:
            content.update("Press [bold]r[/bold] to compute VaR, or wait for auto-refresh...")
            return

        r = self._var_result
        from rich.text import Text
        t = Text()
        t.append("PORTFOLIO VALUE AT RISK\n\n", style="bold cyan")
        t.append(f"  VaR 95:   ${r.var_95:>10.2f}\n", style="bold")
        t.append(f"  VaR 99:   ${r.var_99:>10.2f}\n", style="bold")
        t.append(f"  CVaR 95:  ${r.cvar_95:>10.2f}\n", style="bold")
        t.append(f"  CVaR 99:  ${r.cvar_99:>10.2f}\n", style="bold")
        t.append(f"  P(ruin):  {r.p_ruin:>11.4f}\n\n", style="bold")

        t.append("COMPONENT VAR\n", style="bold cyan")
        if r.component_var is not None and len(r.component_var) > 0:
            for i, pos in enumerate(self.book_state.positions):
                if i < len(r.component_var):
                    cv = r.component_var[i]
                    t.append(f"  {pos.contract_id:<20} ${cv:>8.2f}\n")
        content.update(t)

    def _refresh_kelly_panel(self):
        content = self.query_one("#kelly-content", Static)
        if self._kelly_result is None:
            content.update("Waiting for Kelly computation...")
            return

        kr = self._kelly_result
        from rich.text import Text
        t = Text()
        t.append("KELLY OPTIMAL SIZING\n\n", style="bold cyan")
        bankroll = self.book_state.bankroll
        t.append(f"  Bankroll: ${bankroll:,.2f}", style="bold")
        t.append(f"  (Cash: ${self.book_state.cash_balance:,.2f} + Portfolio: ${self.book_state.portfolio_value:,.2f})\n\n", style="dim")
        t.append(f"  {'Contract':<20} {'Raw':>8} {'Target$':>9} {'Current$':>10} {'Trade':>8}\n", style="bold dim")
        t.append(f"  {'─' * 59}\n", style="dim")
        for i, cid in enumerate(kr.contract_ids):
            raw = kr.raw_kelly[i]
            tgt_dollars = kr.target_fractions[i] * bankroll
            pos = self.book_state.positions[i] if i < len(self.book_state.positions) else None
            if pos:
                current_dollars = pos.quantity * ((1.0 - pos.entry_price) if pos.quantity < 0 else pos.entry_price)
            else:
                current_dollars = 0.0
            trade_dollars = tgt_dollars - current_dollars
            trade_style = "green" if trade_dollars > 0.01 else "red" if trade_dollars < -0.01 else "dim"
            t.append(f"  {cid:<20} {raw:>+8.4f} {tgt_dollars:>+8.2f}  {current_dollars:>+8.2f}  ")
            t.append(f"{trade_dollars:>+8.2f}\n", style=trade_style)
        content.update(t)

    def _refresh_liquidity_table(self):
        rows, keys = [], []
        for m in self._liquidity_metrics:
            rows.append((
                m.contract_id, f"{m.spread_pct:.3f}",
                str(m.depth_at_best_bid), str(m.depth_at_best_ask),
                f"${m.liquidation_slippage:.2f}", m.liquidity_flag,
            ))
            keys.append(m.contract_id)
        self.query_one("#liquidity-table", CachedDataTable).update_rows(rows, keys)

    def _refresh_scenario_panel(self):
        content = self.query_one("#scenario-content", Static)
        from rich.text import Text
        import os
        t = Text()
        t.append("SCENARIO STRESS TESTS\n\n", style="bold cyan")

        if not os.path.exists("scenarios.json"):
            t.append("  No scenarios.json found.\n", style="dim")
            t.append("  Create scenarios.json to run stress tests.\n", style="dim")
            content.update(t)
            return

        try:
            from src.scenario import load_scenarios_from_json, run_scenario_library
            scenarios = load_scenarios_from_json("scenarios.json")
            if not scenarios:
                t.append("  No scenarios defined.\n", style="dim")
                content.update(t)
                return

            pos_dicts = [p.model_dump() for p in self.book_state.positions]
            var_99 = self._var_result.var_99 if self._var_result else None
            results = run_scenario_library(pos_dicts, scenarios, {}, var_99)

            for r in results:
                style = "bold red" if r.exceeds_var99 else "bold"
                flag = " [EXCEEDS VaR99]" if r.exceeds_var99 else ""
                t.append(f"  {r.scenario.name}: ", style="bold")
                t.append(f"${r.pnl:>+10.2f}{flag}\n", style=style)
                for cid, pnl in r.position_pnls.items():
                    t.append(f"    {cid}: ${pnl:>+.2f}\n", style="dim")
                t.append("\n")

        except Exception as e:
            t.append(f"  Error: {e}\n", style="red")

        content.update(t)

    def _refresh_docs_panel(self):
        content = self.query_one("#docs-content", Static)
        from rich.text import Text
        t = Text()

        t.append("KALSIM RISK DESK — DOCUMENTATION\n", style="bold cyan")
        t.append("=" * 60 + "\n\n")

        t.append("1. POSITIONS\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("Portfolio overview showing all open contracts.\n\n")
        t.append("  Contract  ", style="bold")
        t.append("Kalshi ticker (e.g. KXBTC-26031-B5499)\n")
        t.append("  Qty       ", style="bold")
        t.append("Number of contracts held. Positive = long YES,\n")
        t.append("            negative = short YES (equivalent to long NO).\n")
        t.append("  Entry     ", style="bold")
        t.append("Average price paid per contract (0.00–1.00).\n")
        t.append("  Mid       ", style="bold")
        t.append("Current bid-ask midpoint, recomputed live from the\n")
        t.append("            orderbook: (best_yes_bid + best_yes_ask) / 2.\n")
        t.append("  Edge      ", style="bold")
        t.append("model_prob − market_prob. How much you believe the\n")
        t.append("            contract is mispriced. Positive = you think\n")
        t.append("            YES is underpriced. Currently model_prob\n")
        t.append("            defaults to market_prob unless overridden.\n")
        t.append("  PnL       ", style="bold")
        t.append("Unrealized P&L: qty × (current_mid − entry_price).\n")
        t.append("            Mark-to-market, not accounting for fees.\n")
        t.append("  TTE       ", style="bold")
        t.append("Time to expiration in days (e.g. 14.3d).\n")
        t.append("  Flag      ", style="bold")
        t.append("Liquidity flag: NORMAL / WATCH / CRITICAL.\n")
        t.append("            See Liquidity section for thresholds.\n\n")

        t.append("2. ORDERBOOK\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("Select a contract from the top table to see its live\n")
        t.append("orderbook. Shows YES bids and NO bids (asks) sorted by\n")
        t.append("price. Updated via WebSocket deltas in real time.\n\n")

        t.append("3. VaR / RISK\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("Monte Carlo simulation (20,000 paths) of portfolio P&L\n")
        t.append("assuming binary resolution of all contracts.\n\n")
        t.append("Method:\n", style="bold")
        t.append("  1. Draw correlated standard normals (Cholesky decomp)\n")
        t.append("  2. Transform to uniform [0,1] via normal CDF\n")
        t.append("  3. Resolve: if U < model_prob → YES, else NO\n")
        t.append("  4. P&L per contract:\n")
        t.append("       Long YES:  +qty×(1−entry) if YES, −qty×entry if NO\n")
        t.append("       Short YES: −qty×(1−entry) if YES, +qty×entry if NO\n")
        t.append("  5. In the worst 5% of sims, subtract liquidation slippage\n\n")
        t.append("Metrics:\n", style="bold")
        t.append("  VaR 95    ", style="bold")
        t.append("95th percentile of losses. You have a 5% chance\n")
        t.append("            of losing more than this amount.\n")
        t.append("  VaR 99    ", style="bold")
        t.append("99th percentile of losses. 1% chance of exceeding.\n")
        t.append("  CVaR 95   ", style="bold")
        t.append("Conditional VaR (Expected Shortfall). Average loss\n")
        t.append("            in the worst 5% of scenarios. Always ≥ VaR 95.\n")
        t.append("            Answers: \"when things go bad, how bad?\"\n")
        t.append("  CVaR 99   ", style="bold")
        t.append("Average loss in the worst 1% of scenarios.\n")
        t.append("            More extreme tail measure than CVaR 95.\n\n")
        t.append("  P(ruin)   ", style="bold")
        t.append("Fraction of simulations where total loss ≥ max\n")
        t.append("            possible loss across all active positions.\n")
        t.append("            Max loss: Σ |qty|×entry for longs,\n")
        t.append("            Σ |qty|×(1−entry) for shorts. Cash excluded.\n")
        t.append("            A P(ruin) of 0.02 means 2% of simulations\n")
        t.append("            wiped out your entire invested capital.\n\n")
        t.append("Component VaR:\n", style="bold")
        t.append("  Per-position marginal contribution to portfolio VaR.\n")
        t.append("  Computed as average loss of each position in the\n")
        t.append("  worst 5% of portfolio-level simulations. Shows which\n")
        t.append("  positions drive your tail risk.\n\n")

        t.append("4. KELLY OPTIMAL SIZING\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("Kelly criterion position sizing to maximize long-run\n")
        t.append("growth rate, scaled down for safety.\n\n")
        t.append("Columns:\n", style="bold")
        t.append("  Raw       ", style="bold")
        t.append("Full Kelly fraction for each contract:\n")
        t.append("            f* = (model_prob − market_prob) / (1 − market_prob)\n")
        t.append("            Zeroed if |edge| < 3c (min_edge gate).\n")
        t.append("            This is the theoretical bankroll fraction.\n\n")
        t.append("  Target$   ", style="bold")
        t.append("Dollar amount to hold in this position.\n")
        t.append("            Raw × 0.25 (quarter-Kelly) × bankroll,\n")
        t.append("            then constrained:\n")
        t.append("            • Per-contract cap: ±5% of bankroll\n")
        t.append("            • Liquidity cap: from orderbook depth\n")
        t.append("            • Cluster cap: 15% per correlated group\n\n")
        t.append("  Current$  ", style="bold")
        t.append("Dollar value currently held: qty × entry_price.\n\n")
        t.append("  Trade     ", style="bold")
        t.append("Target$ − Current$. Dollar amount to buy (+) or\n")
        t.append("            sell (−) to reach the target allocation.\n")
        t.append("            Zeroed if |trade| < 0.5% of bankroll.\n\n")
        t.append("  Bankroll is fetched live from your Kalshi account:\n")
        t.append("  bankroll = cash_balance + portfolio_value.\n\n")

        t.append("5. SCENARIOS\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("Deterministic stress tests. Define hypothetical outcomes\n")
        t.append("and see exact P&L impact on your portfolio.\n\n")

        t.append("Adding scenarios:\n", style="bold")
        t.append("  Use the input form at the top of the Scenarios tab.\n")
        t.append("  Fill in the JSON template and press Submit.\n")
        t.append("  Valid scenarios are saved to scenarios.json and appear\n")
        t.append("  in the results panel immediately.\n\n")

        t.append("JSON fields:\n", style="bold")
        t.append("  name              ", style="bold")
        t.append("(required) Scenario label shown in results.\n")
        t.append("                    Must be a non-empty string.\n\n")
        t.append("  world_state       ", style="bold")
        t.append("(required) Object describing the scenario state.\n")
        t.append("                    Used by callable resolution rules.\n")
        t.append("                    Can be {} if using overrides only.\n\n")
        t.append("  description       ", style="bold")
        t.append("(optional) Free-text description. Default \"\".\n\n")

        t.append("  resolution_overrides\n", style="bold")
        t.append("                    (optional) Object mapping contract IDs\n")
        t.append("                    to \"YES\" or \"NO\". Forces the contract\n")
        t.append("                    to resolve at $1.00 or $0.00.\n")
        t.append("                    P&L = qty × (settle − entry).\n")
        t.append("                    Values must be exactly \"YES\" or \"NO\".\n\n")

        t.append("  probability_overrides\n", style="bold")
        t.append("                    (optional) Object mapping contract IDs\n")
        t.append("                    to a probability in [0, 1]. Computes\n")
        t.append("                    expected value P&L instead of binary:\n")
        t.append("                    P&L = qty × (prob − entry).\n")
        t.append("                    Use for \"what if the market moves to\n")
        t.append("                    this probability\" analysis.\n\n")

        t.append("Constraints:\n", style="bold")
        t.append("  • A contract ID cannot appear in both resolution_overrides\n")
        t.append("    and probability_overrides (mutually exclusive).\n")
        t.append("  • resolution_overrides values: only \"YES\" or \"NO\".\n")
        t.append("  • probability_overrides values: number in [0, 1].\n\n")

        t.append("Priority chain:\n", style="bold")
        t.append("  When computing P&L for each position, the first match wins:\n")
        t.append("  1. probability_overrides → expected value P&L\n")
        t.append("  2. resolution_overrides  → binary settle at $1/$0\n")
        t.append("  3. resolution_rules      → callable logic (if defined)\n")
        t.append("  4. fallthrough            → mark-to-market (mid − entry)\n\n")

        t.append("Output:\n", style="bold")
        t.append("  • Total P&L per scenario + per-position breakdown\n")
        t.append("  • [EXCEEDS VaR99] flag if scenario loss > VaR 99\n\n")

        t.append("Example:\n", style="bold")
        t.append('  {\n', style="dim")
        t.append('    "name": "Fed holds + BTC rallies",\n', style="dim")
        t.append('    "world_state": {"fed": "hold"},\n', style="dim")
        t.append('    "resolution_overrides": {"FED-HOLD": "YES"},\n', style="dim")
        t.append('    "probability_overrides": {"KXBTC-26031": 0.85}\n', style="dim")
        t.append('  }\n\n', style="dim")

        t.append("6. LIQUIDITY\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("Per-contract liquidity analysis.\n\n")
        t.append("Columns:\n", style="bold")
        t.append("  Spread%   ", style="bold")
        t.append("Bid-ask spread as a fraction of midpoint:\n")
        t.append("            (best_ask − best_bid) / mid\n")
        t.append("            Percentage of mid, not of $1.00. This\n")
        t.append("            normalizes across price levels — a 1c spread\n")
        t.append("            at 50c mid is 2%, but at 10c mid is 10%.\n")
        t.append("            Kalshi prices YES bids directly; the YES ask\n")
        t.append("            is derived: yes_ask = 1.00 − best_no_bid.\n\n")
        t.append("  BidDepth  ", style="bold")
        t.append("Number of contracts at the best YES bid level.\n")
        t.append("  AskDepth  ", style="bold")
        t.append("Number of contracts at the best NO bid level\n")
        t.append("            (equivalent to best YES ask depth).\n\n")
        t.append("  Slippage  ", style="bold")
        t.append("Estimated dollar cost to fully exit your position\n")
        t.append("            at current book depth. Walks the orderbook\n")
        t.append("            level-by-level, computing VWAP of the exit:\n")
        t.append("              Long:  sell into YES bids, unfilled → $0\n")
        t.append("              Short: buy from YES asks, unfilled → $1\n")
        t.append("            Slippage = |mid − vwap| × |qty|\n")
        t.append("            Higher slippage = thinner book = harder exit.\n\n")
        t.append("  Flag      ", style="bold")
        t.append("Liquidity classification:\n\n")
        t.append("    NORMAL   ", style="bold green")
        t.append("TTE ≥ 14 days AND spread ≤ 5%\n")
        t.append("             Comfortable liquidity. No action needed.\n\n")
        t.append("    WATCH    ", style="bold yellow")
        t.append("TTE < 14 days OR spread > 5%\n")
        t.append("             Approaching expiry or wide spread.\n")
        t.append("             Monitor position closely.\n\n")
        t.append("    CRITICAL ", style="bold red")
        t.append("TTE < 3 days\n")
        t.append("             Near-expiry. Very tight window to exit.\n")
        t.append("             Exits may face severe slippage.\n\n")

        t.append("KEYBINDINGS\n", style="bold cyan")
        t.append("-" * 40 + "\n")
        t.append("  1-7       Switch tabs (1:Pos … 6:Liq 7:Docs)\n")
        t.append("  r         Refresh risk computations\n")
        t.append("  arrows    Navigate within/between panels\n")
        t.append("  escape    Return focus to tab bar\n")
        t.append("  q         Quit\n")

        content.update(t)

    def _run_risk_computations(self):
        """Run VaR, Kelly, and liquidity in a background worker."""
        if not self.book_state.positions:
            return
        self.run_worker(self._compute_risk, thread=True, exclusive=True, group="risk")

    def _compute_risk(self):
        """Heavy computation — runs in a thread worker."""
        from src.var_engine import simulate_pnl
        from src.kelly import kelly_optimize
        from src.liquidity import compute_liquidity_metrics

        positions = self.book_state.positions
        if not positions:
            return

        pos_dicts = [p.model_dump() for p in positions]
        n = len(pos_dicts)

        corr = np.eye(n)
        try:
            var_result = simulate_pnl(pos_dicts, corr, n_sims=100_000, seed=42)
            self._var_result = var_result
        except Exception:
            pass

        try:
            bankroll = self.book_state.bankroll or 1.0
            kelly_result = kelly_optimize(pos_dicts, bankroll=bankroll, kelly_fraction=0.25)
            self._kelly_result = kelly_result
        except Exception:
            pass

        metrics = []
        for pos in positions:
            ob = self.book_state.get_orderbook_for_api(pos.contract_id)
            if ob is None:
                ob = {"yes": [], "no": []}
            try:
                m = compute_liquidity_metrics(
                    pos.contract_id, ob, quantity=pos.quantity,
                    entry_price=pos.entry_price, tte_days=pos.tte_days,
                )
                metrics.append(m)
            except Exception:
                pass
        self._liquidity_metrics = metrics

        self.call_from_thread(self._post_risk_refresh)

    def _post_risk_refresh(self):
        self._refresh_positions_table()
        self._refresh_ob_positions_table()
        self._refresh_var_panel()
        self._refresh_kelly_panel()
        self._refresh_liquidity_table()
        self._refresh_scenario_panel()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if event.data_table.id == "ob-positions-table":
            row_key = event.row_key
            self._selected_ticker = str(row_key.value) if row_key else None
            self._refresh_orderbook()

    def action_quit(self):
        self.exit()

    def action_refresh(self):
        self._refresh_positions_table()
        self._run_risk_computations()
        self.notify("Refreshing risk computations...", timeout=2)

    def action_tab(self, tab_id: str):
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

    def action_focus_tabs(self):
        self.query_one(Tabs).focus()

    def on_scenario_input_submitted(self, event: ScenarioInput.Submitted):
        from src.scenario import append_scenario_to_json
        try:
            append_scenario_to_json("scenarios.json", event.scenario)
            self._refresh_scenario_panel()
            self.notify(f"Scenario '{event.scenario.name}' saved", timeout=3)
        except Exception as e:
            self.notify(f"Save failed: {e}", severity="error", timeout=5)
