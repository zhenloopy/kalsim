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


@dataclass
class ScenarioResult:
    scenario: Scenario
    pnl: float
    position_pnls: dict[str, float]
    exceeds_var99: bool


def resolve_contract(contract_id: str, world_state: dict, resolution_rules: dict) -> Resolution:
    """Map a world state to a contract resolution using provided rules.

    resolution_rules: {contract_id: callable(world_state) -> Resolution}
    """
    if contract_id not in resolution_rules:
        return Resolution.INDETERMINATE
    return resolution_rules[contract_id](world_state)


def compute_scenario_pnl(positions: list[dict], scenario: Scenario,
                          resolution_rules: dict) -> ScenarioResult:
    """Compute deterministic P&L for a scenario.

    positions: list of dicts with keys:
        - contract_id, quantity, entry_price, current_mid
    """
    total_pnl = 0.0
    position_pnls = {}

    for pos in positions:
        cid = pos["contract_id"]
        qty = pos["quantity"]
        entry = pos["entry_price"]
        mid = pos.get("current_mid", entry)

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
        )
        for s in data
    ]
