import requests
from datetime import datetime, timezone


class KalshiClient:
    def __init__(self, config):
        self.base_url = config.base_url.rstrip("/")
        self.session = requests.Session()
        self.token = None
        self._config = config

    def login(self):
        if self._config.api_key:
            self.session.headers["Authorization"] = f"Bearer {self._config.api_key}"
            return
        resp = self.session.post(f"{self.base_url}/login", json={
            "email": self._config.email,
            "password": self._config.password,
        })
        resp.raise_for_status()
        self.token = resp.json()["token"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"

    def get_positions(self):
        resp = self.session.get(f"{self.base_url}/portfolio/positions", params={"limit": 1000})
        resp.raise_for_status()
        data = resp.json()
        positions = data.get("market_positions", data.get("positions", []))
        return [p for p in positions if p.get("total_traded", 0) != 0 or abs(p.get("position", 0)) > 0]

    def get_market(self, ticker):
        resp = self.session.get(f"{self.base_url}/markets/{ticker}")
        resp.raise_for_status()
        return resp.json().get("market", resp.json())

    def get_orderbook(self, ticker):
        resp = self.session.get(f"{self.base_url}/markets/{ticker}/orderbook")
        resp.raise_for_status()
        return resp.json().get("orderbook", resp.json())
