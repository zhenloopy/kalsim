import pytest
import json
import tempfile
from pathlib import Path
from src.scenario import (
    Resolution,
    Scenario,
    resolve_contract,
    compute_scenario_pnl,
    run_scenario_library,
    load_scenarios_from_json,
)


def make_positions():
    return [
        {"contract_id": "FED-HOLD", "quantity": 100, "entry_price": 0.60, "current_mid": 0.65},
        {"contract_id": "CPI-HIGH", "quantity": 50, "entry_price": 0.40, "current_mid": 0.45},
        {"contract_id": "ELECTION-A", "quantity": -30, "entry_price": 0.55, "current_mid": 0.50},
    ]


def worst_case_rules():
    """Rules that resolve every position against the holder."""
    return {
        "FED-HOLD": lambda ws: Resolution.NO,    # long loses
        "CPI-HIGH": lambda ws: Resolution.NO,    # long loses
        "ELECTION-A": lambda ws: Resolution.YES,  # short loses
    }


def partial_rules():
    """Only some contracts have rules."""
    return {
        "FED-HOLD": lambda ws: Resolution.YES if ws.get("fed") == "hold" else Resolution.NO,
    }


class TestResolution:
    def test_known_contract(self):
        rules = {"A": lambda ws: Resolution.YES}
        assert resolve_contract("A", {}, rules) == Resolution.YES

    def test_unknown_contract(self):
        assert resolve_contract("UNKNOWN", {}, {}) == Resolution.INDETERMINATE


class TestScenarioPnl:
    def test_worst_case_max_loss(self):
        """Resolving all positions against you should equal maximum possible loss."""
        positions = make_positions()
        scenario = Scenario("worst", {"fed": "hike", "cpi": "low", "election": "A"})
        result = compute_scenario_pnl(positions, scenario, worst_case_rules())

        # FED-HOLD: long 100 at 0.60, resolves NO → PnL = 100 * (0 - 0.60) = -60
        # CPI-HIGH: long 50 at 0.40, resolves NO → PnL = 50 * (0 - 0.40) = -20
        # ELECTION-A: short 30 at 0.55, resolves YES → PnL = -30 * (1 - 0.55) = -13.5
        expected = -60.0 + -20.0 + -13.5
        assert abs(result.pnl - expected) < 1e-10

    def test_best_case(self):
        """Resolving all positions in your favor."""
        positions = make_positions()
        rules = {
            "FED-HOLD": lambda ws: Resolution.YES,
            "CPI-HIGH": lambda ws: Resolution.YES,
            "ELECTION-A": lambda ws: Resolution.NO,
        }
        scenario = Scenario("best", {})
        result = compute_scenario_pnl(positions, scenario, rules)

        # FED-HOLD: 100 * (1 - 0.60) = 40
        # CPI-HIGH: 50 * (1 - 0.40) = 30
        # ELECTION-A: -30 * (0 - 0.55) = 16.5
        expected = 40.0 + 30.0 + 16.5
        assert abs(result.pnl - expected) < 1e-10

    def test_no_overlap_zero_impact(self):
        """Scenario with no matching contracts → all indeterminate → PnL from mid-entry diff."""
        positions = make_positions()
        scenario = Scenario("unrelated", {"weather": "sunny"})
        result = compute_scenario_pnl(positions, scenario, {})

        # All indeterminate: PnL = qty * (mid - entry)
        expected = (100 * (0.65 - 0.60) + 50 * (0.45 - 0.40) + -30 * (0.50 - 0.55))
        assert abs(result.pnl - expected) < 1e-10

    def test_partial_resolution(self):
        """Some contracts resolved, others indeterminate."""
        positions = make_positions()
        scenario = Scenario("fed_hold", {"fed": "hold"})
        result = compute_scenario_pnl(positions, scenario, partial_rules())

        # FED-HOLD: YES → 100 * (1 - 0.60) = 40
        # CPI-HIGH: indeterminate → 50 * (0.45 - 0.40) = 2.5
        # ELECTION-A: indeterminate → -30 * (0.50 - 0.55) = 1.5
        expected = 40.0 + 2.5 + 1.5
        assert abs(result.pnl - expected) < 1e-10

    def test_position_pnl_breakdown(self):
        positions = make_positions()
        scenario = Scenario("worst", {})
        result = compute_scenario_pnl(positions, scenario, worst_case_rules())
        assert "FED-HOLD" in result.position_pnls
        assert "CPI-HIGH" in result.position_pnls
        assert abs(result.position_pnls["FED-HOLD"] - (-60.0)) < 1e-10


class TestScenarioLibrary:
    def test_flag_exceeds_var99(self):
        positions = make_positions()
        scenarios = [
            Scenario("worst", {}),
            Scenario("mild", {}),
        ]
        rules_worst = worst_case_rules()
        rules_mild = {"FED-HOLD": lambda ws: Resolution.YES}

        # Run with combined rules (worst for "worst" scenario)
        # Simplify: just use worst-case rules for all
        results = run_scenario_library(positions, scenarios, rules_worst, var_99=50.0)

        # Worst case loss = 93.5, which exceeds var_99=50
        assert results[0].exceeds_var99 is True

    def test_no_flag_when_under_var99(self):
        positions = [{"contract_id": "A", "quantity": 1, "entry_price": 0.50, "current_mid": 0.50}]
        scenarios = [Scenario("x", {})]
        rules = {"A": lambda ws: Resolution.NO}
        results = run_scenario_library(positions, scenarios, rules, var_99=100.0)
        assert results[0].exceeds_var99 is False


class TestJsonLoading:
    def test_load_from_file(self):
        data = [
            {"name": "scenario1", "world_state": {"fed": "hold"}, "description": "test"},
            {"name": "scenario2", "world_state": {"cpi": "high"}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        scenarios = load_scenarios_from_json(path)
        assert len(scenarios) == 2
        assert scenarios[0].name == "scenario1"
        assert scenarios[0].world_state == {"fed": "hold"}
        Path(path).unlink()
