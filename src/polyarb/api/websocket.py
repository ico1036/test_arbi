"""
WebSocket Client - Real-time price streaming
wss://ws-subscriptions-clob.polymarket.com
"""
import json
import asyncio
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime
import websockets
from websockets.exceptions import ConnectionClosed

from ..config import config


class WebSocketClient:
    """
    WebSocket client for real-time Polymarket data.

    Usage:
        async with WebSocketClient() as ws:
            await ws.subscribe(token_ids)
            async for message in ws.listen():
                process(message)
    """

    def __init__(self, url: Optional[str] = None):
        self.url = url or config.api.ws_clob
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._subscribed_tokens: List[str] = []
        self._callbacks: List[Callable[[Dict], None]] = []
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self._ws = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            )
            self._running = True
            self._reconnect_delay = 1.0  # Reset on successful connect
            print(f"[WS] Connected to {self.url}")
        except Exception as e:
            print(f"[WS] Connection failed: {e}")
            raise

    async def close(self):
        """Close WebSocket connection"""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        print("[WS] Connection closed")

    async def subscribe(self, token_ids: List[str]):
        """Subscribe to market data for given tokens"""
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        self._subscribed_tokens = token_ids

        msg = {"type": "MARKET", "assets_ids": token_ids}

        await self._ws.send(json.dumps(msg))
        print(f"[WS] Subscribed to {len(token_ids)} tokens")

    async def unsubscribe(self, token_ids: List[str]):
        """Unsubscribe from specific tokens"""
        if not self._ws:
            return

        msg = {"assets_ids": token_ids, "operation": "unsubscribe"}

        await self._ws.send(json.dumps(msg))
        self._subscribed_tokens = [
            t for t in self._subscribed_tokens if t not in token_ids
        ]

    async def add_subscription(self, token_ids: List[str]):
        """Add tokens to existing subscription"""
        if not self._ws:
            return

        msg = {"assets_ids": token_ids, "operation": "subscribe"}

        await self._ws.send(json.dumps(msg))
        self._subscribed_tokens.extend(token_ids)

    def add_callback(self, callback: Callable[[Dict], None]):
        """Add callback for incoming messages"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Dict], None]):
        """Remove a callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def listen(self):
        """
        Generator that yields incoming messages.
        Handles reconnection automatically.
        """
        while self._running:
            try:
                if not self._ws:
                    await self.connect()
                    if self._subscribed_tokens:
                        await self.subscribe(self._subscribed_tokens)

                message = await asyncio.wait_for(self._ws.recv(), timeout=30)
                data = json.loads(message)

                # Invoke callbacks
                for callback in self._callbacks:
                    try:
                        callback(data)
                    except Exception as e:
                        print(f"[WS] Callback error: {e}")

                yield data

            except asyncio.TimeoutError:
                # No message received, continue listening
                continue

            except ConnectionClosed as e:
                print(f"[WS] Connection closed: {e}")
                self._ws = None

                if self._running:
                    print(f"[WS] Reconnecting in {self._reconnect_delay}s...")
                    await asyncio.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._max_reconnect_delay
                    )

            except Exception as e:
                print(f"[WS] Error: {e}")
                if self._running:
                    await asyncio.sleep(1)

    async def listen_for_duration(self, seconds: float) -> List[Dict]:
        """Listen for a specific duration and return all messages"""
        messages = []
        start = asyncio.get_event_loop().time()

        async for msg in self.listen():
            messages.append(msg)
            if asyncio.get_event_loop().time() - start >= seconds:
                break

        return messages


class PriceTracker:
    """
    Track real-time prices from WebSocket stream.
    Maintains latest prices for subscribed tokens.
    """

    def __init__(self):
        self.prices: Dict[str, float] = {}
        self.last_update: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def update(self, message: Dict):
        """Process WebSocket message and update prices"""
        async with self._lock:
            # Handle different message formats
            if isinstance(message, list):
                for item in message:
                    await self._process_item(item)
            else:
                await self._process_item(message)

    async def _process_item(self, item: Dict):
        """Process a single message item"""
        if not isinstance(item, dict):
            return

        # Extract asset_id and price from various message formats
        asset_id = item.get("asset_id")

        # Check for price in different fields
        price = None
        if "price" in item:
            price = item["price"]
        elif "price_changes" in item:
            changes = item["price_changes"]
            if changes and isinstance(changes, list):
                # Get the latest price change
                price = changes[-1].get("price")

        if asset_id and price is not None:
            try:
                self.prices[asset_id] = float(price)
                self.last_update[asset_id] = datetime.now()
            except (ValueError, TypeError):
                pass

    def get_price(self, token_id: str) -> Optional[float]:
        """Get latest price for a token"""
        return self.prices.get(token_id)

    def get_all_prices(self) -> Dict[str, float]:
        """Get all tracked prices"""
        return self.prices.copy()

    def is_stale(self, token_id: str, max_age_seconds: float = 60) -> bool:
        """Check if a price is stale"""
        if token_id not in self.last_update:
            return True
        age = (datetime.now() - self.last_update[token_id]).total_seconds()
        return age > max_age_seconds
