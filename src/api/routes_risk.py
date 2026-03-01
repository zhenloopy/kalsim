import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.deps import app_state
from src.api.schemas import (
    VaRResponse, KellyResponse, KellyAllocationResponse,
    LiquidityMetricResponse, ScenarioResultResponse, ScenarioPositionPnl,
)

router = APIRouter(prefix="/api/risk")


@router.get("/var")
def get_var() -> VaRResponse | None:
    rc = app_state.risk_cache
    if rc.var_result is None:
        return None
    r = rc.var_result
    bs = app_state.book_state
    component_var = []
    if r.component_var is not None and len(r.component_var) > 0:
        for i, pos in enumerate(bs.positions):
            if i < len(r.component_var):
                component_var.append({
                    "contract_id": pos.contract_id,
                    "value": float(r.component_var[i]),
                })
    return VaRResponse(
        var_95=r.var_95,
        var_99=r.var_99,
        cvar_95=r.cvar_95,
        cvar_99=r.cvar_99,
        p_ruin=r.p_ruin,
        component_var=component_var,
        pnl_distribution=r.pnl_distribution.tolist(),
    )


@router.get("/kelly")
def get_kelly() -> KellyResponse | None:
    rc = app_state.risk_cache
    if rc.kelly_result is None:
        return None
    kr = rc.kelly_result
    bs = app_state.book_state
    bankroll = bs.bankroll or 1.0

    allocations = []
    for i, cid in enumerate(kr.contract_ids):
        tgt = kr.target_fractions[i] * bankroll
        pos = bs.positions[i] if i < len(bs.positions) else None
        current = pos.quantity * ((1.0 - pos.entry_price) if pos.quantity < 0 else pos.entry_price) if pos else 0.0
        allocations.append(KellyAllocationResponse(
            contract_id=cid,
            raw_kelly=float(kr.raw_kelly[i]),
            target_fraction=float(kr.target_fractions[i]),
            target_dollars=float(tgt),
            current_dollars=float(current),
            trade_dollars=float(tgt - current),
        ))
    return KellyResponse(
        bankroll=bankroll,
        cash=bs.cash_balance,
        portfolio_value=bs.portfolio_value,
        allocations=allocations,
    )


@router.get("/liquidity")
def get_liquidity() -> list[LiquidityMetricResponse]:
    rc = app_state.risk_cache
    return [
        LiquidityMetricResponse(
            contract_id=m.contract_id,
            spread_pct=m.spread_pct,
            depth_at_best_bid=m.depth_at_best_bid,
            depth_at_best_ask=m.depth_at_best_ask,
            liquidation_slippage=m.liquidation_slippage,
            liquidity_flag=m.liquidity_flag,
        )
        for m in rc.liquidity_metrics
    ]


@router.get("/scenarios")
def get_scenarios() -> list[ScenarioResultResponse]:
    from src.scenario import load_scenarios_from_json, run_scenario_library

    if not Path("scenarios.json").exists():
        return []

    try:
        scenarios = load_scenarios_from_json("scenarios.json")
    except Exception:
        return []

    if not scenarios:
        return []

    bs = app_state.book_state
    pos_dicts = [p.model_dump() for p in bs.positions]
    rc = app_state.risk_cache
    var_99 = rc.var_result.var_99 if rc.var_result else None
    results = run_scenario_library(pos_dicts, scenarios, {}, var_99)

    return [
        ScenarioResultResponse(
            name=r.scenario.name,
            description=r.scenario.description,
            pnl=r.pnl,
            exceeds_var99=r.exceeds_var99,
            position_pnls=[
                ScenarioPositionPnl(contract_id=cid, pnl=pnl)
                for cid, pnl in r.position_pnls.items()
            ],
        )
        for r in results
    ]


class ScenarioSubmission(BaseModel):
    json_str: str


@router.post("/scenarios")
def submit_scenario(body: ScenarioSubmission) -> ScenarioResultResponse:
    from src.scenario import validate_scenario_json, append_scenario_to_json, compute_scenario_pnl

    scenario, err = validate_scenario_json(body.json_str)
    if err:
        raise HTTPException(status_code=400, detail=err)

    append_scenario_to_json("scenarios.json", scenario)

    bs = app_state.book_state
    pos_dicts = [p.model_dump() for p in bs.positions]
    result = compute_scenario_pnl(pos_dicts, scenario, {})

    rc = app_state.risk_cache
    if rc.var_result:
        result.exceeds_var99 = (-result.pnl) > rc.var_result.var_99

    return ScenarioResultResponse(
        name=result.scenario.name,
        description=result.scenario.description,
        pnl=result.pnl,
        exceeds_var99=result.exceeds_var99,
        position_pnls=[
            ScenarioPositionPnl(contract_id=cid, pnl=pnl)
            for cid, pnl in result.position_pnls.items()
        ],
    )


@router.post("/refresh")
async def refresh_risk():
    from src.api.server import _compute_risk
    await asyncio.to_thread(_compute_risk)
    return {"status": "ok"}
