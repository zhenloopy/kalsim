import json
from textual.widgets import Static, DataTable, Label, Button, TextArea
from textual.containers import Vertical, Horizontal
from textual.message import Message
from rich.text import Text

from src.scenario import Scenario, validate_scenario_json

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
