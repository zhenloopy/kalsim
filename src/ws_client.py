import asyncio
import base64
import json
import logging
import time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

WS_PATH = "/trade-api/ws/v2"


class KalshiWS:
    """Async websocket client for Kalshi streaming data.

    Subscribes to orderbook_delta, ticker, and fill channels.
    Updates BookState on every message.
    """

    def __init__(self, config, book_state):
        self.config = config
        self.book_state = book_state
        self._ws = None
        self._running = False
        self._sub_id = 0
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._task = None

        key_data = config.private_key.replace("\\n", "\n")
        self._private_key = serialization.load_pem_private_key(
            key_data.encode(), password=None
        )
        self._key_id = config.key_id

        base = config.base_url.replace("https://", "wss://").replace("/trade-api/v2", "")
        self._ws_url = f"{base}{WS_PATH}"

    def _auth_headers(self):
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}GET{WS_PATH}".encode("utf-8")
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

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.book_state.ws_connected = False

    async def _run_loop(self):
        import websockets

        while self._running:
            try:
                headers = self._auth_headers()
                async with websockets.connect(
                    self._ws_url,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self.book_state.ws_connected = True
                    self._reconnect_delay = 1.0
                    logger.info("WebSocket connected")

                    await self._subscribe_all()

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg)
                            self._handle_message(msg)
                        except json.JSONDecodeError:
                            logger.warning("Non-JSON ws message")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"WS connection lost: {e}")
                self.book_state.ws_connected = False
                if self._running:
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._max_reconnect_delay
                    )

    async def _subscribe_all(self):
        tickers = self.book_state.get_tickers()
        if not tickers:
            return

        await self._subscribe("orderbook_delta", market_tickers=tickers)
        await self._subscribe("ticker", market_tickers=tickers)
        await self._subscribe("fill")

    async def _subscribe(self, channel, **params):
        self._sub_id += 1
        msg = {
            "id": self._sub_id,
            "cmd": "subscribe",
            "params": {"channels": [channel], **params},
        }
        if self._ws:
            logger.info(f"Subscribing: {msg}")
            await self._ws.send(json.dumps(msg))

    async def subscribe_tickers(self, tickers: list[str]):
        """Subscribe to new tickers after initial connection."""
        if not self._ws or not tickers:
            return
        await self._subscribe("orderbook_delta", market_tickers=tickers)
        await self._subscribe("ticker", market_tickers=tickers)

    def _handle_message(self, msg):
        msg_type = msg.get("type", "")
        data = msg.get("msg", {})
        logger.debug(f"WS recv type={msg_type} data={data}")

        if msg_type == "orderbook_snapshot":
            ticker = data.get("market_ticker", "")
            yes_levels = data.get("yes", [])
            no_levels = data.get("no", [])
            self.book_state.apply_orderbook_snapshot(ticker, yes_levels, no_levels)

        elif msg_type == "orderbook_delta":
            ticker = data.get("market_ticker", "")
            price = data.get("price", 0)
            delta = data.get("delta", 0)
            side = data.get("side", "yes")
            self.book_state.apply_orderbook_delta(ticker, price, delta, side)

        elif msg_type == "ticker":
            ticker = data.get("market_ticker", "")
            self.book_state.apply_ticker_update(ticker, data)

        elif msg_type == "fill":
            ticker = data.get("market_ticker", "")
            side = data.get("side", "yes")
            count = data.get("count", 0)
            price = data.get("yes_price", data.get("no_price", 0))
            new_ticker = self.book_state.apply_fill(ticker, side, count, price)
            if new_ticker:
                asyncio.create_task(self._on_new_position(new_ticker))

        elif msg_type == "error":
            code = data.get("code", "?")
            emsg = data.get("msg", "unknown")
            logger.error(f"WS error {code}: {emsg}")

    async def _on_new_position(self, ticker: str):
        await self.subscribe_tickers([ticker])
        try:
            from src.kalshi_client import KalshiClient
            client = await asyncio.to_thread(KalshiClient, self.config)
            market = await asyncio.to_thread(client.get_market, ticker)
            orderbook = await asyncio.to_thread(client.get_orderbook, ticker)
            self.book_state.update_position_metadata(ticker, market, orderbook)
            logger.info(f"Fetched metadata for new position: {ticker}")
        except Exception as e:
            logger.warning(f"Failed to fetch metadata for {ticker}: {e}")
