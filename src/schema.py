from pydantic import BaseModel, model_validator
from datetime import datetime


class Position(BaseModel):
    contract_id: str
    title: str = ""
    platform: str
    canonical_event_id: str
    quantity: int
    entry_price: float
    current_mid: float
    market_prob: float
    model_prob: float
    edge: float
    resolves_at: datetime
    tte_days: float
    fee_adjusted_breakeven: float

    @property
    def market_value(self) -> float:
        if self.quantity >= 0:
            return self.quantity * self.current_mid
        return abs(self.quantity) * (1.0 - self.current_mid)

    @model_validator(mode="before")
    @classmethod
    def compute_derived_fields(cls, data):
        if isinstance(data, dict):
            if "model_prob" not in data or data["model_prob"] is None:
                data["model_prob"] = data.get("market_prob", data.get("current_mid", 0.0))
            if "edge" not in data or data["edge"] is None:
                data["edge"] = data["model_prob"] - data["market_prob"]
        return data
