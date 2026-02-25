from dataclasses import dataclass


@dataclass
class LiquidityMetrics:
    contract_id: str
    spread_pct: float
    depth_at_best_bid: int
    depth_at_best_ask: int
    amihud: float | None
    position_vs_adv: float | None
    liquidation_slippage: float
    liquidity_flag: str


def compute_spread(orderbook):
    """Spread as fraction of mid. Orderbook prices in cents [0,100]."""
    yes_bids = orderbook.get("yes", [])
    no_bids = orderbook.get("no", [])
    if not yes_bids or not no_bids:
        return float("inf"), None, None

    best_bid = yes_bids[0][0] / 100.0
    best_ask = 1.0 - no_bids[0][0] / 100.0

    if best_ask <= best_bid:
        best_ask = best_bid + 0.01

    mid = (best_bid + best_ask) / 2.0
    spread_pct = (best_ask - best_bid) / mid if mid > 0 else float("inf")
    return spread_pct, best_bid, best_ask


def compute_depth_at_best(orderbook):
    yes_bids = orderbook.get("yes", [])
    no_bids = orderbook.get("no", [])
    bid_depth = yes_bids[0][1] if yes_bids else 0
    ask_depth = no_bids[0][1] if no_bids else 0
    return bid_depth, ask_depth


def compute_liquidation_slippage(orderbook, quantity):
    """Walk the order book to estimate exit cost.

    For long (quantity > 0): selling YES → consuming bid side.
    For short (quantity < 0): buying YES → consuming ask side (NO bid side).
    Returns slippage as a positive dollar amount (cost to exit).
    """
    abs_qty = abs(quantity)
    if abs_qty == 0:
        return 0.0

    yes_bids = orderbook.get("yes", [])
    no_bids = orderbook.get("no", [])

    if quantity > 0:
        levels = [(p / 100.0, q) for p, q in yes_bids]
    else:
        levels = [(1.0 - p / 100.0, q) for p, q in no_bids]

    if not levels:
        return abs_qty * 1.0

    mid_bid = levels[0][0] if quantity > 0 else None
    mid_ask = levels[0][0] if quantity < 0 else None

    best_bid_price = yes_bids[0][0] / 100.0 if yes_bids else 0.5
    best_ask_price = (1.0 - no_bids[0][0] / 100.0) if no_bids else 0.5
    mid = (best_bid_price + best_ask_price) / 2.0

    filled = 0
    total_proceeds = 0.0
    for price, depth in levels:
        can_fill = min(depth, abs_qty - filled)
        total_proceeds += can_fill * price
        filled += can_fill
        if filled >= abs_qty:
            break

    if filled < abs_qty:
        unfilled = abs_qty - filled
        if quantity > 0:
            total_proceeds += unfilled * 0.0
        else:
            total_proceeds += unfilled * 1.0

    vwap = total_proceeds / abs_qty
    if quantity > 0:
        slippage = (mid - vwap) * abs_qty
    else:
        slippage = (vwap - mid) * abs_qty

    return max(slippage, 0.0)


def compute_amihud(price_changes, dollar_volumes):
    """Amihud illiquidity: mean(|Δprice| / dollar_volume) over available data."""
    if not price_changes or not dollar_volumes:
        return None
    ratios = []
    for dp, dv in zip(price_changes, dollar_volumes):
        if dv > 0:
            ratios.append(abs(dp) / dv)
    return sum(ratios) / len(ratios) if ratios else None


def compute_position_vs_adv(quantity, entry_price, avg_daily_volume_dollars):
    """Position notional as multiple of average daily volume."""
    if avg_daily_volume_dollars is None or avg_daily_volume_dollars <= 0:
        return None
    position_notional = abs(quantity) * entry_price
    return position_notional / avg_daily_volume_dollars


def classify_liquidity(tte_days, spread_pct):
    if tte_days < 3:
        return "CRITICAL"
    if tte_days < 14 or spread_pct > 0.05:
        return "WATCH"
    return "NORMAL"


def compute_liquidity_metrics(
    contract_id, orderbook, quantity, entry_price, tte_days,
    price_changes=None, dollar_volumes=None, avg_daily_volume=None,
):
    spread_pct, _, _ = compute_spread(orderbook)
    bid_depth, ask_depth = compute_depth_at_best(orderbook)
    slippage = compute_liquidation_slippage(orderbook, quantity)
    amihud = compute_amihud(price_changes, dollar_volumes)
    pos_vs_adv = compute_position_vs_adv(quantity, entry_price, avg_daily_volume)
    flag = classify_liquidity(tte_days, spread_pct)

    return LiquidityMetrics(
        contract_id=contract_id,
        spread_pct=spread_pct,
        depth_at_best_bid=bid_depth,
        depth_at_best_ask=ask_depth,
        amihud=amihud,
        position_vs_adv=pos_vs_adv,
        liquidation_slippage=slippage,
        liquidity_flag=flag,
    )
