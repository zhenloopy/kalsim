import base64
import time
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class KalshiClient:
    def __init__(self, config):
        self.base_url = config.base_url.rstrip("/")
        self.session = requests.Session()
        self._key_id = config.key_id
        key_data = config.private_key.replace("\\n", "\n")
        self._private_key = serialization.load_pem_private_key(
            key_data.encode(), password=None
        )

    def _sign(self, method, path):
        timestamp = str(int(time.time() * 1000))
        path_without_query = path.split("?")[0]
        message = f"{timestamp}{method}{path_without_query}".encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
        }

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        headers = self._sign(method.upper(), f"/trade-api/v2{path}")
        resp = self.session.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_positions(self):
        data = self._request("GET", "/portfolio/positions", params={"limit": 1000})
        positions = data.get("market_positions", data.get("positions", []))
        return [p for p in positions if p.get("total_traded", 0) != 0 or abs(p.get("position", 0)) > 0]

    def get_market(self, ticker):
        data = self._request("GET", f"/markets/{ticker}")
        return data.get("market", data)

    def get_orderbook(self, ticker):
        data = self._request("GET", f"/markets/{ticker}/orderbook")
        return data.get("orderbook", data)

    def get_market_history(self, ticker, limit=1000):
        try:
            data = self._request("GET", f"/markets/{ticker}/history", params={"limit": limit})
            return data.get("history", data.get("snapshots", []))
        except Exception:
            return []
