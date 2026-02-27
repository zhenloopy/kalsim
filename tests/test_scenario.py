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
    validate_scenario_json,
    append_scenario_to_json,
)


def make_positions():
    return [
        {"contract_id": "FED-HOLD", "quantity": 100, "entry_price": 0.60, "current_mid": 0.65},
        {"contract_id": "CPI-HIGH", "quantity": 50, "entry_price": 0.40, "current_mid": 0.45},
        {"contract_id": "ELECTION-A", "quantity": -30, "entry_price": 0.55, "current_mid": 0.50},
    ]


def worst_case_rules():
    return {
        "FED-HOLD": lambda ws: Resolution.NO,
        "CPI-HIGH": lambda ws: Resolution.NO,
        "ELECTION-A": lambda ws: Resolution.YES,
    }


def partial_rules():
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
        positions = make_positions()
        scenario = Scenario("worst", {"fed": "hike", "cpi": "low", "election": "A"})
        result = compute_scenario_pnl(positions, scenario, worst_case_rules())

        # FED-HOLD: long 100 at 0.60, resolves NO -> 100 * (0 - 0.60) = -60
        # CPI-HIGH: long 50 at 0.40, resolves NO -> 50 * (0 - 0.40) = -20
        # ELECTION-A: short 30 at 0.55, resolves YES -> -30 * (1 - 0.55) = -13.5
        expected = -60.0 + -20.0 + -13.5
        assert abs(result.pnl - expected) < 1e-10

    def test_best_case(self):
        positions = make_positions()
        rules = {
            "FED-HOLD": lambda ws: Resolution.YES,
            "CPI-HIGH": lambda ws: Resolution.YES,
            "ELECTION-A": lambda ws: Resolution.NO,
        }
        scenario = Scenario("best", {})
        result = compute_scenario_pnl(positions, scenario, rules)

        expected = 40.0 + 30.0 + 16.5
        assert abs(result.pnl - expected) < 1e-10

    def test_no_overlap_zero_impact(self):
        positions = make_positions()
        scenario = Scenario("unrelated", {"weather": "sunny"})
        result = compute_scenario_pnl(positions, scenario, {})

        expected = (100 * (0.65 - 0.60) + 50 * (0.45 - 0.40) + -30 * (0.50 - 0.55))
        assert abs(result.pnl - expected) < 1e-10

    def test_partial_resolution(self):
        positions = make_positions()
        scenario = Scenario("fed_hold", {"fed": "hold"})
        result = compute_scenario_pnl(positions, scenario, partial_rules())

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
        results = run_scenario_library(positions, scenarios, worst_case_rules(), var_99=50.0)
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

    def test_load_with_overrides(self):
        data = [{
            "name": "with_overrides",
            "world_state": {},
            "resolution_overrides": {"A": "YES"},
            "probability_overrides": {"B": 0.75},
        }]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        scenarios = load_scenarios_from_json(path)
        assert scenarios[0].resolution_overrides == {"A": "YES"}
        assert scenarios[0].probability_overrides == {"B": 0.75}
        Path(path).unlink()


class TestValidateScenarioJson:
    def test_valid_minimal(self):
        raw = json.dumps({"name": "test", "world_state": {"k": "v"}})
        scenario, err = validate_scenario_json(raw)
        assert err is None
        assert scenario.name == "test"
        assert scenario.resolution_overrides == {}
        assert scenario.probability_overrides == {}

    def test_valid_all_fields(self):
        raw = json.dumps({
            "name": "full",
            "world_state": {"fed": "hold"},
            "description": "desc",
            "resolution_overrides": {"A": "YES", "B": "NO"},
            "probability_overrides": {"C": 0.5},
        })
        scenario, err = validate_scenario_json(raw)
        assert err is None
        assert scenario.resolution_overrides == {"A": "YES", "B": "NO"}
        assert scenario.probability_overrides == {"C": 0.5}

    def test_invalid_json_syntax(self):
        _, err = validate_scenario_json("{bad json")
        assert err is not None
        assert "Invalid JSON" in err

    def test_missing_name(self):
        raw = json.dumps({"world_state": {}})
        _, err = validate_scenario_json(raw)
        assert "name" in err.lower()

    def test_empty_name(self):
        raw = json.dumps({"name": "  ", "world_state": {}})
        _, err = validate_scenario_json(raw)
        assert "name" in err.lower()

    def test_missing_world_state(self):
        raw = json.dumps({"name": "test"})
        _, err = validate_scenario_json(raw)
        assert "world_state" in err

    def test_bad_resolution_value(self):
        raw = json.dumps({
            "name": "test", "world_state": {},
            "resolution_overrides": {"A": "MAYBE"},
        })
        _, err = validate_scenario_json(raw)
        assert "YES" in err and "NO" in err

    def test_probability_out_of_range(self):
        raw = json.dumps({
            "name": "test", "world_state": {},
            "probability_overrides": {"A": 1.5},
        })
        _, err = validate_scenario_json(raw)
        assert "[0, 1]" in err

    def test_probability_negative(self):
        raw = json.dumps({
            "name": "test", "world_state": {},
            "probability_overrides": {"A": -0.1},
        })
        _, err = validate_scenario_json(raw)
        assert "[0, 1]" in err

    def test_overlap_between_overrides(self):
        raw = json.dumps({
            "name": "test", "world_state": {},
            "resolution_overrides": {"A": "YES"},
            "probability_overrides": {"A": 0.5},
        })
        _, err = validate_scenario_json(raw)
        assert "both" in err.lower()

    def test_int_coercion_for_probability(self):
        raw = json.dumps({
            "name": "test", "world_state": {},
            "probability_overrides": {"A": 1},
        })
        scenario, err = validate_scenario_json(raw)
        assert err is None
        assert scenario.probability_overrides["A"] == 1.0
        assert isinstance(scenario.probability_overrides["A"], float)

    def test_not_a_dict(self):
        _, err = validate_scenario_json(json.dumps([1, 2, 3]))
        assert "object" in err.lower()


class TestProbabilityOverridePnl:
    def test_long_expected_value(self):
        # 100 contracts long at 0.40, model prob = 0.70
        # EV PnL = 100 * (0.70 - 0.40) = 30
        positions = [{"contract_id": "A", "quantity": 100, "entry_price": 0.40, "current_mid": 0.40}]
        scenario = Scenario("ev_test", {}, probability_overrides={"A": 0.70})
        result = compute_scenario_pnl(positions, scenario, {})
        assert abs(result.pnl - 30.0) < 1e-10

    def test_short_expected_value(self):
        # -50 contracts at 0.60, model prob = 0.80
        # EV PnL = -50 * (0.80 - 0.60) = -10
        positions = [{"contract_id": "A", "quantity": -50, "entry_price": 0.60, "current_mid": 0.60}]
        scenario = Scenario("ev_short", {}, probability_overrides={"A": 0.80})
        result = compute_scenario_pnl(positions, scenario, {})
        assert abs(result.pnl - (-10.0)) < 1e-10

    def test_prob_zero_equals_resolution_no(self):
        positions = [{"contract_id": "A", "quantity": 100, "entry_price": 0.60, "current_mid": 0.60}]
        prob_scenario = Scenario("prob0", {}, probability_overrides={"A": 0.0})
        res_scenario = Scenario("resno", {}, resolution_overrides={"A": "NO"})
        prob_result = compute_scenario_pnl(positions, prob_scenario, {})
        res_result = compute_scenario_pnl(positions, res_scenario, {})
        assert abs(prob_result.pnl - res_result.pnl) < 1e-10

    def test_prob_one_equals_resolution_yes(self):
        positions = [{"contract_id": "A", "quantity": 100, "entry_price": 0.60, "current_mid": 0.60}]
        prob_scenario = Scenario("prob1", {}, probability_overrides={"A": 1.0})
        res_scenario = Scenario("resyes", {}, resolution_overrides={"A": "YES"})
        prob_result = compute_scenario_pnl(positions, prob_scenario, {})
        res_result = compute_scenario_pnl(positions, res_scenario, {})
        assert abs(prob_result.pnl - res_result.pnl) < 1e-10


class TestResolutionOverridePnl:
    def test_override_beats_rules(self):
        # resolution_overrides should take priority over resolution_rules
        positions = [{"contract_id": "A", "quantity": 100, "entry_price": 0.50, "current_mid": 0.50}]
        rules = {"A": lambda ws: Resolution.NO}
        scenario = Scenario("override", {}, resolution_overrides={"A": "YES"})
        result = compute_scenario_pnl(positions, scenario, rules)
        # Override says YES: 100 * (1 - 0.50) = 50
        assert abs(result.pnl - 50.0) < 1e-10

    def test_mixed_overrides_and_indeterminate(self):
        positions = [
            {"contract_id": "A", "quantity": 100, "entry_price": 0.40, "current_mid": 0.50},
            {"contract_id": "B", "quantity": -50, "entry_price": 0.60, "current_mid": 0.55},
            {"contract_id": "C", "quantity": 20, "entry_price": 0.30, "current_mid": 0.35},
        ]
        scenario = Scenario(
            "mixed", {},
            resolution_overrides={"A": "YES"},
            probability_overrides={"B": 0.80},
        )
        result = compute_scenario_pnl(positions, scenario, {})
        # A: resolution YES -> 100 * (1 - 0.40) = 60
        # B: prob 0.80 -> -50 * (0.80 - 0.60) = -10
        # C: indeterminate -> 20 * (0.35 - 0.30) = 1
        assert abs(result.pnl - 51.0) < 1e-10


class TestAppendScenario:
    def test_creates_new_file(self, tmp_path):
        path = tmp_path / "new_scenarios.json"
        scenario = Scenario("new", {"fed": "cut"}, "testing")
        append_scenario_to_json(path, scenario)

        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "new"
        assert data[0]["world_state"] == {"fed": "cut"}

    def test_appends_to_existing(self, tmp_path):
        path = tmp_path / "existing.json"
        with open(path, "w") as f:
            json.dump([{"name": "first", "world_state": {}, "description": ""}], f)

        scenario = Scenario("second", {"x": "y"}, resolution_overrides={"A": "YES"})
        append_scenario_to_json(path, scenario)

        with open(path) as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[1]["name"] == "second"
        assert data[1]["resolution_overrides"] == {"A": "YES"}

    def test_omits_empty_overrides(self, tmp_path):
        path = tmp_path / "clean.json"
        scenario = Scenario("minimal", {})
        append_scenario_to_json(path, scenario)

        with open(path) as f:
            data = json.load(f)
        assert "resolution_overrides" not in data[0]
        assert "probability_overrides" not in data[0]
