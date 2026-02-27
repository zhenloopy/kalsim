from textual.widgets import Static, DataTable, Label
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from rich.text import Text


class CachedDataTable(DataTable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_rows: list[tuple] = []

    def update_rows(self, rows: list[tuple], keys: list[str] | None = None):
        if rows == self._cached_rows:
            return
        self._cached_rows = list(rows)
        saved_row = self.cursor_row
        self.clear()
        for i, row in enumerate(rows):
            key = keys[i] if keys else None
            self.add_row(*row, key=key)
        if self.row_count > 0:
            self.move_cursor(row=min(max(0, saved_row), self.row_count - 1), animate=False)


class RiskSidebar(Vertical):
    """Always-visible risk summary sidebar."""

    nav_skip = True

    var_95 = reactive(0.0)
    var_99 = reactive(0.0)
    cvar_95 = reactive(0.0)
    cvar_99 = reactive(0.0)
    p_ruin = reactive(0.0)
    total_pnl = reactive(0.0)
    ws_status = reactive(False)
    flags: reactive[list] = reactive(list, always_update=True)

    def compose(self):
        yield Label("RISK SUMMARY", id="sidebar-title")
        yield Static(id="risk-metrics")
        yield Static(id="pnl-display")
        yield Static(id="flags-display")
        yield Static(id="ws-status-display")

    def _render_risk(self):
        metrics = self.query_one("#risk-metrics", Static)
        t = Text()
        t.append("VaR 95:  ", style="dim")
        t.append(f"${self.var_95:>8.2f}\n", style="bold red" if self.var_95 > 0 else "bold green")
        t.append("VaR 99:  ", style="dim")
        t.append(f"${self.var_99:>8.2f}\n", style="bold red" if self.var_99 > 0 else "bold green")
        t.append("CVaR 95: ", style="dim")
        t.append(f"${self.cvar_95:>8.2f}\n", style="bold red" if self.cvar_95 > 0 else "bold green")
        t.append("CVaR 99: ", style="dim")
        t.append(f"${self.cvar_99:>8.2f}\n", style="bold red" if self.cvar_99 > 0 else "bold green")
        t.append("P(ruin): ", style="dim")
        style = "bold red" if self.p_ruin > 0.01 else "bold yellow" if self.p_ruin > 0.001 else "bold green"
        t.append(f"  {self.p_ruin:>7.4f}\n", style=style)
        metrics.update(t)

    def _render_pnl(self):
        pnl = self.query_one("#pnl-display", Static)
        t = Text()
        t.append("\nTotal PnL: ", style="dim")
        style = "bold green" if self.total_pnl >= 0 else "bold red"
        t.append(f"${self.total_pnl:>+.2f}\n", style=style)
        pnl.update(t)

    def _render_flags(self):
        display = self.query_one("#flags-display", Static)
        t = Text()
        t.append("\nLIQUIDITY FLAGS\n", style="bold")
        if not self.flags:
            t.append("  No flags", style="dim")
        else:
            for flag_info in self.flags[:5]:
                cid = flag_info.get("id", "?")
                flag = flag_info.get("flag", "NORMAL")
                style = {"CRITICAL": "bold red", "WATCH": "bold yellow"}.get(flag, "green")
                t.append(f"  {cid[:16]:<16} ", style="dim")
                t.append(f"{flag}\n", style=style)
        display.update(t)

    def _render_ws(self):
        ws = self.query_one("#ws-status-display", Static)
        t = Text()
        t.append("\n")
        if self.ws_status:
            t.append("  WS: CONNECTED", style="bold green")
        else:
            t.append("  WS: DISCONNECTED", style="bold red")
        ws.update(t)

    def watch_var_95(self, _):
        self._render_risk()

    def watch_var_99(self, _):
        self._render_risk()

    def watch_cvar_95(self, _):
        self._render_risk()

    def watch_cvar_99(self, _):
        self._render_risk()

    def watch_p_ruin(self, _):
        self._render_risk()

    def watch_total_pnl(self, _):
        self._render_pnl()

    def watch_ws_status(self, _):
        self._render_ws()

    def watch_flags(self, _):
        self._render_flags()

    def on_mount(self):
        self._render_risk()
        self._render_pnl()
        self._render_flags()
        self._render_ws()


class OrderbookDisplay(Vertical):
    """Live orderbook visualization for a selected contract."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_ticker: str | None = None

    def compose(self):
        yield Label("Select a position to view orderbook", id="ob-ticker-label")
        with Horizontal(id="orderbook-container"):
            yield CachedDataTable(id="ob-bids")
            yield CachedDataTable(id="ob-asks")

    def on_mount(self):
        bids = self.query_one("#ob-bids", CachedDataTable)
        bids.add_columns("Bid Qty", "Bid Price")
        bids.cursor_type = "row"

        asks = self.query_one("#ob-asks", CachedDataTable)
        asks.add_columns("Ask Price", "Ask Qty")
        asks.cursor_type = "row"

    def update_orderbook(self, ticker: str, orderbook: dict | None):
        if ticker != self._last_ticker:
            self.query_one("#ob-ticker-label", Label).update(f"Orderbook: {ticker}")
            self._last_ticker = ticker

        if orderbook is None:
            self.query_one("#ob-bids", CachedDataTable).update_rows([])
            self.query_one("#ob-asks", CachedDataTable).update_rows([])
            return

        yes_levels = orderbook.get("yes", [])
        no_levels = orderbook.get("no", [])

        bid_rows = [
            (str(qty), f"{(price / 100.0 if price > 1 else price):.2f}")
            for price, qty in yes_levels[:15]
        ]
        ask_rows = [
            (f"{(1.0 - (price / 100.0 if price > 1 else price)):.2f}", str(qty))
            for price, qty in no_levels[:15]
        ]

        self.query_one("#ob-bids", CachedDataTable).update_rows(bid_rows)
        self.query_one("#ob-asks", CachedDataTable).update_rows(ask_rows)
