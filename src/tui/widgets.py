import json
import time
from datetime import datetime, timezone
from textual.widgets import Static, DataTable, Label, Button, TextArea
from textual.containers import Vertical, Horizontal
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from rich.text import Text
from textual_plotext import PlotextPlot

from src.scenario import Scenario, validate_scenario_json
from src.collector import collector_status, start_collector, stop_collector

SCENARIO_TEMPLATE = json.dumps({
    "name": "",
    "world_state": {},
    "description": "",
    "resolution_overrides": {},
    "probability_overrides": {},
}, indent=2)


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


class ScenarioInput(Vertical):

    class Submitted(Message):
        def __init__(self, scenario: Scenario):
            super().__init__()
            self.scenario = scenario

    def compose(self):
        yield Label("ADD SCENARIO", id="scenario-input-title")
        yield TextArea(SCENARIO_TEMPLATE, language="json", id="scenario-textarea")
        yield Static("", id="scenario-error")
        yield Button("Submit", id="scenario-submit", variant="primary")

    def _submit(self):
        textarea = self.query_one("#scenario-textarea", TextArea)
        error_display = self.query_one("#scenario-error", Static)
        raw = textarea.text

        scenario, err = validate_scenario_json(raw)
        if err:
            error_display.update(Text(err, style="bold red"))
            return

        error_display.update(Text(f"Added: {scenario.name}", style="bold green"))
        textarea.load_text(SCENARIO_TEMPLATE)
        self.post_message(self.Submitted(scenario))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "scenario-submit":
            self._submit()


RANGES = {
    "1H": 3600,
    "6H": 6 * 3600,
    "1D": 86400,
    "1W": 7 * 86400,
    "2W": 14 * 86400,
    "1M": 30 * 86400,
    "6M": 180 * 86400,
    "1Y": 365 * 86400,
    "5Y": 5 * 365 * 86400,
}

RANGE_KEYS = list(RANGES.keys())


class NavChart(Vertical):
    active_range: reactive[str] = reactive("1W")

    def __init__(self, nav_store=None, **kwargs):
        super().__init__(**kwargs)
        self._nav_store = nav_store

    def compose(self):
        with Horizontal(id="nav-range-bar"):
            for key in RANGE_KEYS:
                cls = "range-btn-active" if key == self.active_range else "range-btn"
                yield Button(key, id=f"range-{key}", classes=cls)
        yield PlotextPlot(id="nav-plot")

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""
        if not btn_id.startswith("range-"):
            return
        key = btn_id.removeprefix("range-")
        if key in RANGES:
            self.active_range = key

    def watch_active_range(self, old_val: str, new_val: str):
        for key in RANGE_KEYS:
            try:
                btn = self.query_one(f"#range-{key}", Button)
                btn.set_classes("range-btn-active" if key == new_val else "range-btn")
            except Exception:
                pass
        self.replot()

    def replot(self):
        if self._nav_store is None:
            return
        try:
            plot_widget = self.query_one("#nav-plot", PlotextPlot)
        except Exception:
            return
        plt = plot_widget.plt
        plt.clear_figure()

        now = time.time()
        span = RANGES.get(self.active_range, RANGES["1W"])
        start = now - span
        snapshots = self._nav_store.query(start, now, max_points=500)

        if not snapshots:
            plt.title("No NAV history yet")
            plot_widget.refresh()
            return

        times = [s.timestamp_utc for s in snapshots]
        navs = [s.nav for s in snapshots]

        labels = []
        for t in times:
            dt = datetime.fromtimestamp(t, tz=timezone.utc)
            if span <= 86400:
                labels.append(dt.strftime("%H:%M"))
            elif span <= 14 * 86400:
                labels.append(dt.strftime("%m/%d %H:%M"))
            else:
                labels.append(dt.strftime("%m/%d"))

        nav_min, nav_max = min(navs), max(navs)
        pad_lo = abs(nav_min) * 0.1 if nav_min != 0 else 1.0
        pad_hi = abs(nav_max) * 0.1 if nav_max != 0 else 1.0
        plt.ylim(nav_min - pad_lo, nav_max + pad_hi)

        plt.plot(navs, marker="braille")
        plt.title(f"NAV — {self.active_range}")
        plt.ylabel("$")
        n = len(labels)
        if n > 0:
            step = max(1, n // 8)
            indices = list(range(0, n, step))
            plt.xticks(indices, [labels[i] for i in indices])

        plot_widget.refresh()


INTERVALS = {
    "1m": 60,
    "5m": 300,
    "30m": 1800,
    "1hr": 3600,
    "24hr": 86400,
}

INTERVAL_KEYS = list(INTERVALS.keys())


class SettingsPanel(Vertical):

    class CollectorToggled(Message):
        def __init__(self, running: bool):
            super().__init__()
            self.running = running

    class IntervalChanged(Message):
        def __init__(self, label: str, seconds: int):
            super().__init__()
            self.label = label
            self.seconds = seconds

    active_interval: reactive[str] = reactive("1m")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def compose(self):
        yield Label("SETTINGS", id="settings-title")

        yield Label("NAV Collector", id="collector-section-label")
        with Horizontal(id="collector-controls"):
            yield Button("ON", id="collector-on-btn", variant="success")
            yield Button("OFF", id="collector-off-btn", variant="error")
        yield Static("", id="collector-status-display")

        yield Label("Collection Interval", id="interval-section-label")
        with Horizontal(id="interval-bar"):
            for key in INTERVAL_KEYS:
                cls = "interval-btn-active" if key == self.active_interval else "interval-btn"
                yield Button(key, id=f"interval-{key}", classes=cls)
        yield Static("", id="interval-status-display")

    def on_mount(self):
        self._refresh_status()

    def _refresh_status(self):
        running = collector_status()
        status = self.query_one("#collector-status-display", Static)
        if running:
            status.update(Text("Collector is running", style="bold green"))
        else:
            status.update(Text("Collector is stopped", style="bold red"))

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id or ""

        if btn_id == "collector-on-btn":
            if not collector_status():
                seconds = INTERVALS[self.active_interval]
                start_collector(seconds)
            self._refresh_status()
            self.post_message(self.CollectorToggled(True))
            return

        if btn_id == "collector-off-btn":
            if collector_status():
                stop_collector()
            self._refresh_status()
            self.post_message(self.CollectorToggled(False))
            return

        if btn_id.startswith("interval-"):
            key = btn_id.removeprefix("interval-")
            if key in INTERVALS:
                self.active_interval = key
                self.post_message(self.IntervalChanged(key, INTERVALS[key]))

    def watch_active_interval(self, old_val: str, new_val: str):
        for key in INTERVAL_KEYS:
            try:
                btn = self.query_one(f"#interval-{key}", Button)
                btn.set_classes("interval-btn-active" if key == new_val else "interval-btn")
            except Exception:
                pass
        try:
            info = self.query_one("#interval-status-display", Static)
            info.update(Text(f"Interval set to {new_val}", style="dim"))
        except NoMatches:
            return
        if collector_status():
            stop_collector()
            start_collector(INTERVALS[new_val])
            self._refresh_status()
