import os
from dataclasses import dataclass


@dataclass
class KalshiConfig:
    base_url: str = os.getenv("KALSHI_API_URL", "https://trading-api.kalshi.com/trade-api/v2")
    api_key: str = os.getenv("KALSHI_API_KEY", "")
    email: str = os.getenv("KALSHI_EMAIL", "")
    password: str = os.getenv("KALSHI_PASSWORD", "")
    fee_rate: float = float(os.getenv("KALSHI_FEE_RATE", "0.07"))


@dataclass
class FeedConfig:
    kalshi: KalshiConfig = None

    def __post_init__(self):
        if self.kalshi is None:
            self.kalshi = KalshiConfig()
