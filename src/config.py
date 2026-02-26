import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class KalshiConfig:
    base_url: str = os.getenv("KALSHI_API_URL", "https://api.elections.kalshi.com/trade-api/v2")
    key_id: str = os.getenv("KALSHI_KEY_ID", "")
    private_key: str = os.getenv("KALSHI_PRIVATE_KEY", "")
    fee_rate: float = float(os.getenv("KALSHI_FEE_RATE", "0.07"))


@dataclass
class FeedConfig:
    kalshi: KalshiConfig = None

    def __post_init__(self):
        if self.kalshi is None:
            self.kalshi = KalshiConfig()
