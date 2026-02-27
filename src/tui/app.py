import asyncio
import time
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import (
    Header, Footer, Static, DataTable, Label, TabbedContent, TabPane, Tabs,
)
from textual.worker import Worker, WorkerState

from src.book_state import BookState
from src.tui.widgets import RiskSidebar, OrderbookDisplay, CachedDataTable
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
        with Horizontal(id="main-container"):
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
                    yield VerticalScroll(Static(id="scenario-content"), id="scenario-panel")
                with TabPane("Liquidity", id="liquidity"):
                    yield CachedDataTable(id="liquidity-table")
            yield RiskSidebar(id="sidebar")
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
        self._refresh_sidebar()
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
        self._refresh_sidebar()
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
        self._refresh_sidebar()
        self._update_subtitle()

    def _refresh_positions_table(self):
        rows, keys = [], []
        for pos in self.book_state.positions:
            pnl = self.book_state.get_position_pnl(pos)
            flag = self._get_flag_for(pos.contract_id)
            rows.append((
                pos.contract_id, str(pos.quantity),
                f"{pos.entry_price:.2f}", f"{pos.current_mid:.2f}",
                f"{pos.edge:+.3f}", f"${pnl:+.2f}",
                f"{pos.tte_days:.1f}d", flag,
            ))
            keys.append(pos.contract_id)
        self.query_one("#positions-table", CachedDataTable).update_rows(rows, keys)

    def _refresh_ob_positions_table(self):
        rows, keys = [], []
        for pos in self.book_state.positions:
            rows.append((pos.contract_id, str(pos.quantity), f"{pos.current_mid:.2f}"))
            keys.append(pos.contract_id)
        self.query_one("#ob-positions-table", CachedDataTable).update_rows(rows, keys)

    def _get_flag_for(self, contract_id: str) -> str:
        for m in self._liquidity_metrics:
            if m.contract_id == contract_id:
                return m.liquidity_flag
        return "-"

    def _refresh_sidebar(self):
        sidebar = self.query_one("#sidebar", RiskSidebar)
        sidebar.total_pnl = self.book_state.get_total_pnl()
        sidebar.ws_status = self.book_state.ws_connected

        if self._var_result:
            sidebar.var_95 = self._var_result.var_95
            sidebar.var_99 = self._var_result.var_99
            sidebar.cvar_95 = self._var_result.cvar_95
            sidebar.p_ruin = self._var_result.p_ruin

        flags = []
        for m in self._liquidity_metrics:
            if m.liquidity_flag != "NORMAL":
                flags.append({"id": m.contract_id, "flag": m.liquidity_flag})
        sidebar.flags = flags

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
        t.append(f"  {'Contract':<20} {'Raw':>8} {'Target':>8} {'Trade':>8}\n", style="bold dim")
        t.append(f"  {'─' * 48}\n", style="dim")
        for i, cid in enumerate(kr.contract_ids):
            raw = kr.raw_kelly[i]
            tgt = kr.target_fractions[i]
            trade = kr.recommended_trades[i]
            trade_style = "green" if trade > 0.001 else "red" if trade < -0.001 else "dim"
            t.append(f"  {cid:<20} {raw:>+8.4f} {tgt:>+8.4f} ")
            t.append(f"{trade:>+8.4f}\n", style=trade_style)
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
            var_result = simulate_pnl(pos_dicts, corr, n_sims=20_000, seed=42)
            self._var_result = var_result
        except Exception:
            pass

        try:
            kelly_result = kelly_optimize(pos_dicts, bankroll=10_000, kelly_fraction=0.25)
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
        self._refresh_sidebar()
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
