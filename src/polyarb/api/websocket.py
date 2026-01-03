"""
WebSocket Client - Real-time price streaming
wss://ws-subscriptions-clob.polymarket.com
"""
import json
import asyncio
from typing import List, Optional, Callable, Dict, Any, Set
from datetime import datetime
from dataclasses import dataclass, field
import websockets
from websockets.exceptions import ConnectionClosed

from ..config import config


@dataclass
class MarketState:
    """Tracks state of a binary market for arbitrage detection"""
    market_id: str
    question: str
    slug: str
    liquidity: float
    category: str
    yes_token_id: str
    no_token_id: str
    yes_ask: Optional[float] = None
    no_ask: Optional[float] = None
    yes_bid: Optional[float] = None
    no_bid: Optional[float] = None
    last_update: datetime = field(default_factory=datetime.now)

    @property
    def url(self) -> str:
        return f"https://polymarket.com/event/{self.slug}" if self.slug else ""

    def update_price(self, token_id: str, bid: Optional[float], ask: Optional[float]):
        """Update price for a token"""
        if token_id == self.yes_token_id:
            if bid is not None:
                self.yes_bid = bid
            if ask is not None:
                self.yes_ask = ask
        elif token_id == self.no_token_id:
            if bid is not None:
                self.no_bid = bid
            if ask is not None:
                self.no_ask = ask
        self.last_update = datetime.now()

    def check_underpriced(self, min_profit: float) -> Optional[Dict]:
        """Check if market is underpriced (YES_ask + NO_ask < $1)"""
        if self.yes_ask is None or self.no_ask is None:
            return None
        if self.yes_ask <= 0 or self.no_ask <= 0:
            return None

        total_cost = self.yes_ask + self.no_ask
        if total_cost >= 1.0:
            return None

        profit = 1.0 - total_cost
        profit_percent = (profit / total_cost) * 100

        if profit_percent < min_profit:
            return None

        return {
            "type": "BINARY_UNDERPRICED",
            "market_id": self.market_id,
            "question": self.question,
            "url": self.url,
            "yes_ask": self.yes_ask,
            "no_ask": self.no_ask,
            "total_cost": total_cost,
            "profit": profit,
            "profit_percent": profit_percent,
            "liquidity": self.liquidity,
            "category": self.category,
        }

    def check_overpriced(self, min_profit: float) -> Optional[Dict]:
        """Check if market is overpriced (YES_bid + NO_bid > $1)"""
        if self.yes_bid is None or self.no_bid is None:
            return None
        if self.yes_bid <= 0 or self.no_bid <= 0:
            return None

        total_value = self.yes_bid + self.no_bid
        if total_value <= 1.0:
            return None

        profit = total_value - 1.0
        profit_percent = (profit / 1.0) * 100

        if profit_percent < min_profit:
            return None

        return {
            "type": "BINARY_OVERPRICED",
            "market_id": self.market_id,
            "question": self.question,
            "url": self.url,
            "yes_bid": self.yes_bid,
            "no_bid": self.no_bid,
            "total_value": total_value,
            "profit": profit,
            "profit_percent": profit_percent,
            "liquidity": self.liquidity,
            "category": self.category,
        }


@dataclass
class NegRiskEventState:
    """Tracks state of a NegRisk event for arbitrage detection"""
    event_id: str
    title: str
    slug: str
    total_liquidity: float
    # market_id -> (yes_token_id, question)
    markets: Dict[str, tuple] = field(default_factory=dict)
    # yes_token_id -> ask price
    yes_prices: Dict[str, float] = field(default_factory=dict)
    # yes_token_id -> bid price (for NO side = 1 - yes_bid)
    yes_bids: Dict[str, float] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)

    @property
    def url(self) -> str:
        return f"https://polymarket.com/event/{self.slug}" if self.slug else ""

    def update_price(self, token_id: str, bid: Optional[float], ask: Optional[float]):
        """Update YES price for a token"""
        if token_id in self.yes_prices or any(token_id == m[0] for m in self.markets.values()):
            if ask is not None:
                self.yes_prices[token_id] = ask
            if bid is not None:
                self.yes_bids[token_id] = bid
            self.last_update = datetime.now()

    def check_underpriced(self, min_profit: float) -> Optional[Dict]:
        """Check if sum of all YES asks < $1"""
        if len(self.yes_prices) < 3:
            return None

        total_cost = sum(self.yes_prices.values())
        if total_cost >= 1.0:
            return None
        if total_cost <= 0.1:  # Skip if prices too low (likely no liquidity)
            return None

        profit = 1.0 - total_cost
        profit_percent = (profit / total_cost) * 100

        if profit_percent < min_profit:
            return None

        return {
            "type": "NEGRISK_UNDERPRICED",
            "event_id": self.event_id,
            "title": self.title,
            "url": self.url,
            "prices": dict(self.yes_prices),
            "total_cost": total_cost,
            "profit": profit,
            "profit_percent": profit_percent,
            "liquidity": self.total_liquidity,
            "num_outcomes": len(self.yes_prices),
        }

    def check_overpriced(self, min_profit: float) -> Optional[Dict]:
        """Check if sum of all YES bids > $1 (sell opportunity)"""
        if len(self.yes_bids) < 3:
            return None

        total_value = sum(self.yes_bids.values())
        if total_value <= 1.0:
            return None

        profit = total_value - 1.0
        profit_percent = (profit / 1.0) * 100

        if profit_percent < min_profit:
            return None

        return {
            "type": "NEGRISK_OVERPRICED",
            "event_id": self.event_id,
            "title": self.title,
            "url": self.url,
            "prices": dict(self.yes_bids),
            "total_value": total_value,
            "profit": profit,
            "profit_percent": profit_percent,
            "liquidity": self.total_liquidity,
            "num_outcomes": len(self.yes_bids),
        }


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


class RealtimeArbitrageDetector:
    """
    Real-time arbitrage detection using WebSocket price updates.

    Maintains state for all markets and detects opportunities
    as soon as prices change.
    """

    def __init__(
        self,
        min_profit_percent: float = 1.0,
        min_liquidity: float = 1000,
    ):
        self.min_profit = min_profit_percent
        self.min_liquidity = min_liquidity

        # token_id -> MarketState
        self.binary_markets: Dict[str, MarketState] = {}
        # token_id -> market_id mapping
        self.token_to_market: Dict[str, str] = {}

        # event_id -> NegRiskEventState
        self.negrisk_events: Dict[str, NegRiskEventState] = {}
        # token_id -> event_id mapping
        self.token_to_event: Dict[str, str] = {}

        # Track seen opportunities to avoid duplicates
        self.seen_opportunities: Set[str] = set()

        # Callbacks for opportunity detection
        self.on_opportunity: Optional[Callable[[Dict], None]] = None

        # Stats
        self.messages_processed = 0
        self.opportunities_found = 0

    def register_binary_market(
        self,
        market_id: str,
        question: str,
        slug: str,
        liquidity: float,
        category: str,
        yes_token_id: str,
        no_token_id: str,
        yes_ask: Optional[float] = None,
        no_ask: Optional[float] = None,
        yes_bid: Optional[float] = None,
        no_bid: Optional[float] = None,
    ):
        """Register a binary market for monitoring"""
        if liquidity < self.min_liquidity:
            return

        state = MarketState(
            market_id=market_id,
            question=question,
            slug=slug,
            liquidity=liquidity,
            category=category,
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            yes_ask=yes_ask,
            no_ask=no_ask,
            yes_bid=yes_bid,
            no_bid=no_bid,
        )

        self.binary_markets[market_id] = state
        self.token_to_market[yes_token_id] = market_id
        self.token_to_market[no_token_id] = market_id

    def register_negrisk_event(
        self,
        event_id: str,
        title: str,
        slug: str,
        total_liquidity: float,
        markets: List[Dict],  # List of {market_id, yes_token_id, question, yes_ask, yes_bid}
    ):
        """Register a NegRisk event for monitoring"""
        if total_liquidity < self.min_liquidity:
            return

        state = NegRiskEventState(
            event_id=event_id,
            title=title,
            slug=slug,
            total_liquidity=total_liquidity,
        )

        for m in markets:
            market_id = m.get("market_id", "")
            yes_token_id = m.get("yes_token_id", "")
            question = m.get("question", "")

            state.markets[market_id] = (yes_token_id, question)

            if m.get("yes_ask") is not None:
                state.yes_prices[yes_token_id] = m["yes_ask"]
            if m.get("yes_bid") is not None:
                state.yes_bids[yes_token_id] = m["yes_bid"]

            self.token_to_event[yes_token_id] = event_id

        self.negrisk_events[event_id] = state

    def get_all_token_ids(self) -> List[str]:
        """Get all token IDs that need to be subscribed"""
        return list(self.token_to_market.keys()) + list(self.token_to_event.keys())

    def process_message(self, message: Any) -> List[Dict]:
        """
        Process a WebSocket message and check for arbitrage opportunities.
        Returns list of detected opportunities.
        """
        self.messages_processed += 1
        opportunities = []

        # Handle list of updates
        if isinstance(message, list):
            for item in message:
                opps = self._process_single_update(item)
                opportunities.extend(opps)
        else:
            opportunities = self._process_single_update(message)

        return opportunities

    def _process_single_update(self, item: Any) -> List[Dict]:
        """Process a single price update"""
        if not isinstance(item, dict):
            return []

        opportunities = []

        # Extract token_id and prices
        token_id = item.get("asset_id")
        if not token_id:
            return []

        # Parse bid/ask from message
        bid, ask = self._extract_prices(item)

        # Check if this token belongs to a binary market
        if token_id in self.token_to_market:
            market_id = self.token_to_market[token_id]
            if market_id in self.binary_markets:
                state = self.binary_markets[market_id]
                state.update_price(token_id, bid, ask)

                # Check for opportunities
                opp = state.check_underpriced(self.min_profit)
                if opp:
                    opportunities.append(opp)

                opp = state.check_overpriced(self.min_profit)
                if opp:
                    opportunities.append(opp)

        # Check if this token belongs to a NegRisk event
        if token_id in self.token_to_event:
            event_id = self.token_to_event[token_id]
            if event_id in self.negrisk_events:
                state = self.negrisk_events[event_id]
                state.update_price(token_id, bid, ask)

                # Check for opportunities
                opp = state.check_underpriced(self.min_profit)
                if opp:
                    opportunities.append(opp)

                opp = state.check_overpriced(self.min_profit)
                if opp:
                    opportunities.append(opp)

        # Filter duplicates and trigger callbacks
        new_opportunities = []
        for opp in opportunities:
            key = f"{opp.get('type')}_{opp.get('market_id', opp.get('event_id'))}_{opp.get('profit_percent', 0):.1f}"
            if key not in self.seen_opportunities:
                self.seen_opportunities.add(key)
                self.opportunities_found += 1
                new_opportunities.append(opp)

                if self.on_opportunity:
                    self.on_opportunity(opp)

        return new_opportunities

    def _extract_prices(self, item: Dict) -> tuple:
        """Extract bid and ask prices from a WebSocket message"""
        bid = None
        ask = None

        # Different message formats
        if "price" in item:
            # Simple price update - assume it's the mid or ask
            try:
                ask = float(item["price"])
            except (ValueError, TypeError):
                pass

        if "best_bid" in item:
            try:
                bid = float(item["best_bid"])
            except (ValueError, TypeError):
                pass

        if "best_ask" in item:
            try:
                ask = float(item["best_ask"])
            except (ValueError, TypeError):
                pass

        # Handle book updates
        if "bids" in item and item["bids"]:
            try:
                # Best bid is highest price
                bids = item["bids"]
                if isinstance(bids, list) and bids:
                    bid = float(bids[0].get("price", 0))
            except (ValueError, TypeError, IndexError):
                pass

        if "asks" in item and item["asks"]:
            try:
                # Best ask is lowest price
                asks = item["asks"]
                if isinstance(asks, list) and asks:
                    ask = float(asks[0].get("price", 0))
            except (ValueError, TypeError, IndexError):
                pass

        return bid, ask

    def clear_seen(self):
        """Clear seen opportunities (for periodic refresh)"""
        self.seen_opportunities.clear()

    def get_stats(self) -> Dict:
        """Get detector statistics"""
        return {
            "binary_markets": len(self.binary_markets),
            "negrisk_events": len(self.negrisk_events),
            "total_tokens": len(self.token_to_market) + len(self.token_to_event),
            "messages_processed": self.messages_processed,
            "opportunities_found": self.opportunities_found,
        }
