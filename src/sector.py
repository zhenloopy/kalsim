SECTOR_KEYWORDS = {
    "Economics": [
        "FED", "CPI", "GDP", "INFLATION", "JOBS", "UNEMPLOYMENT", "RATE",
        "TREASURY", "YIELD", "RECESSION", "DEBT", "DEFICIT", "PAYROLL",
        "HOUSING", "RETAIL", "WAGE",
    ],
    "Politics": [
        "ELECTION", "PRESIDENT", "SENATE", "HOUSE", "CONGRESS", "VOTE",
        "GOVERNOR", "MAYOR", "TRUMP", "BIDEN", "HARRIS", "APPROVAL",
        "IMPEACH", "SCOTUS", "SUPREME", "LEGISLATION", "BILL",
    ],
    "Sports": [
        "NBA", "NFL", "MLB", "NHL", "FIFA", "TENNIS", "GOLF", "UFC",
        "BOXING", "SUPER-BOWL", "SUPERBOWL", "WORLD-SERIES", "MARCH-MADNESS",
        "NCAA", "SOCCER", "EPL", "CHAMPIONS-LEAGUE",
    ],
    "Crypto": [
        "BTC", "ETH", "BITCOIN", "ETHEREUM", "CRYPTO", "SOL", "DOGE",
        "XRP", "SOLANA",
    ],
    "Climate / Weather": [
        "TEMP", "HURRICANE", "CLIMATE", "WEATHER", "TORNADO", "SNOW",
        "RAIN", "WILDFIRE", "DROUGHT",
    ],
    "Tech / AI": [
        "AI", "GPT", "OPENAI", "ANTHROPIC", "GOOGLE-AI",
    ],
    "Finance": [
        "SP500", "SPX", "NASDAQ", "DOW", "STOCK", "IPO", "EARNINGS",
        "OIL", "GOLD", "COMMODITY",
    ],
}


def classify_sector(event_id: str) -> str:
    upper = event_id.upper()
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in upper:
                return sector
    return "Other"


def compute_sector_breakdown(positions):
    """Compute fraction of capital-at-risk per sector.

    Capital-at-risk: for long YES = qty * entry_price,
    for short YES (long NO) = |qty| * (1 - entry_price).
    """
    sector_exposure = {}
    total = 0.0

    for p in positions:
        qty = p.quantity if isinstance(p.quantity, (int, float)) else p["quantity"]
        entry = p.entry_price if hasattr(p, "entry_price") else p["entry_price"]
        event_id = getattr(p, "canonical_event_id", None) or p.get("contract_id", "")

        if qty > 0:
            exposure = abs(qty) * entry
        else:
            exposure = abs(qty) * (1.0 - entry)

        sector = classify_sector(event_id)
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + exposure
        total += exposure

    if total == 0:
        return {}, 0.0

    breakdown = {s: v / total for s, v in sector_exposure.items()}
    breakdown = dict(sorted(breakdown.items(), key=lambda x: -x[1]))
    return breakdown, total
