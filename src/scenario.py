import json
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class Resolution(Enum):
    YES = "YES"
    NO = "NO"
    INDETERMINATE = "INDETERMINATE"


@dataclass
class Scenario:
    name: str
    world_state: dict[str, str]
    description: str = ""
    resolution_overrides: dict[str, str] = field(default_factory=dict)
    probability_overrides: dict[str, float] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    scenario: Scenario
    pnl: float
    position_pnls: dict[str, float]
    exceeds_var99: bool


def validate_scenario_json(raw: str) -> tuple[Scenario | None, str | None]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"

    if not isinstance(data, dict):
        return None, "Scenario must be a JSON object"

    if "name" not in data or not isinstance(data["name"], str) or not data["name"].strip():
        return None, "Missing or empty 'name' field"

    if "world_state" not in data or not isinstance(data["world_state"], dict):
        return None, "Missing or invalid 'world_state' (must be object)"

    description = data.get("description", "")
    if not isinstance(description, str):
        return None, "'description' must be a string"

    resolution_overrides = data.get("resolution_overrides", {})
    if not isinstance(resolution_overrides, dict):
        return None, "'resolution_overrides' must be an object"
    for cid, val in resolution_overrides.items():
        if val not in ("YES", "NO"):
            return None, f"resolution_overrides['{cid}'] must be \"YES\" or \"NO\", got \"{val}\""

    probability_overrides = data.get("probability_overrides", {})
    if not isinstance(probability_overrides, dict):
        return None, "'probability_overrides' must be an object"
    for cid, val in probability_overrides.items():
        if not isinstance(val, (int, float)):
            return None, f"probability_overrides['{cid}'] must be a number, got {type(val).__name__}"
        if not (0 <= val <= 1):
            return None, f"probability_overrides['{cid}'] must be in [0, 1], got {val}"

    overlap = set(resolution_overrides) & set(probability_overrides)
    if overlap:
        return None, f"Contract(s) in both resolution and probability overrides: {', '.join(sorted(overlap))}"

    prob_overrides_float = {k: float(v) for k, v in probability_overrides.items()}

    scenario = Scenario(
        name=data["name"].strip(),
        world_state=data["world_state"],
        description=description,
        resolution_overrides=resolution_overrides,
        probability_overrides=prob_overrides_float,
    )
    return scenario, None


def resolve_contract(contract_id: str, world_state: dict, resolution_rules: dict) -> Resolution:
    if contract_id not in resolution_rules:
        return Resolution.INDETERMINATE
    return resolution_rules[contract_id](world_state)


def compute_scenario_pnl(positions: list[dict], scenario: Scenario,
                          resolution_rules: dict) -> ScenarioResult:
    total_pnl = 0.0
    position_pnls = {}

    for pos in positions:
        cid = pos["contract_id"]
        qty = pos["quantity"]
        entry = pos["entry_price"]
        mid = pos.get("current_mid", entry)

        if cid in scenario.probability_overrides:
            prob = scenario.probability_overrides[cid]
            pnl = qty * (prob - entry)
        elif cid in scenario.resolution_overrides:
            res = scenario.resolution_overrides[cid]
            if res == "YES":
                pnl = qty * (1.0 - entry)
            else:
                pnl = qty * (0.0 - entry)
        else:
            resolution = resolve_contract(cid, scenario.world_state, resolution_rules)
            if resolution == Resolution.YES:
                pnl = qty * (1.0 - entry)
            elif resolution == Resolution.NO:
                pnl = qty * (0.0 - entry)
            else:
                pnl = qty * (mid - entry)

        position_pnls[cid] = pnl
        total_pnl += pnl

    return ScenarioResult(
        scenario=scenario,
        pnl=total_pnl,
        position_pnls=position_pnls,
        exceeds_var99=False,
    )


def run_scenario_library(
    positions: list[dict],
    scenarios: list[Scenario],
    resolution_rules: dict,
    var_99: float | None = None,
) -> list[ScenarioResult]:
    results = []
    for sc in scenarios:
        result = compute_scenario_pnl(positions, sc, resolution_rules)
        if var_99 is not None:
            result.exceeds_var99 = (-result.pnl) > var_99
        results.append(result)
    return results


def load_scenarios_from_json(path: str | Path) -> list[Scenario]:
    with open(path) as f:
        data = json.load(f)
    return [
        Scenario(
            name=s["name"],
            world_state=s["world_state"],
            description=s.get("description", ""),
            resolution_overrides=s.get("resolution_overrides", {}),
            probability_overrides=s.get("probability_overrides", {}),
        )
        for s in data
    ]


def append_scenario_to_json(path: str | Path, scenario: Scenario):
    path = Path(path)
    if path.exists():
        with open(path) as f:
            data = json.load(f)
    else:
        data = []

    entry = {
        "name": scenario.name,
        "world_state": scenario.world_state,
        "description": scenario.description,
    }
    if scenario.resolution_overrides:
        entry["resolution_overrides"] = scenario.resolution_overrides
    if scenario.probability_overrides:
        entry["probability_overrides"] = scenario.probability_overrides

    data.append(entry)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
