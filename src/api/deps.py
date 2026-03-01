from dataclasses import dataclass, field
import numpy as np

from src.book_state import BookState
from src.nav_store import NavStore
from src.config import KalshiConfig


@dataclass
class RiskCache:
    var_result: object = None
    kelly_result: object = None
    liquidity_metrics: list = field(default_factory=list)


class AppState:
    def __init__(self):
        self.book_state: BookState | None = None
        self.nav_store: NavStore | None = None
        self.kalshi_config: KalshiConfig | None = None
        self.ws_client: object = None
        self.risk_cache: RiskCache = RiskCache()
        self.collector_interval: int = 60


app_state = AppState()
