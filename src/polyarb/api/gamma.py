"""
Gamma API Client - Market discovery and metadata
https://gamma-api.polymarket.com
"""
import json
import asyncio
from typing import List, Optional, Dict, Any
import aiohttp

from ..config import config
from ..models import Market, Token, MarketType


class GammaClient:
    """Async client for Polymarket Gamma API (market discovery)"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or config.api.gamma_api
        self.timeout = aiohttp.ClientTimeout(total=config.api.timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def fetch_markets(
        self,
        limit: int = 500,
        closed: bool = False,
        active: bool = True,
        order_by: str = "liquidityNum",
        ascending: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetch markets from Gamma API.
        Returns raw market data for further processing.
        """
        params = {
            "closed": str(closed).lower(),
            "active": str(active).lower(),
            "limit": limit,
            "order": order_by,
            "ascending": str(ascending).lower(),
        }

        async with self.session.get(
            f"{self.base_url}/markets", params=params
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def fetch_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch events (groups of related markets).
        Useful for finding NegRisk markets.
        """
        params = {"limit": limit, "closed": "false", "active": "true"}

        async with self.session.get(
            f"{self.base_url}/events", params=params
        ) as response:
            response.raise_for_status()
            return await response.json()

    def parse_market(self, raw: Dict[str, Any]) -> Optional[Market]:
        """Parse raw market data into Market model"""
        # Skip if no order book
        if not raw.get("enableOrderBook"):
            return None

        # Parse token IDs
        clob_ids = raw.get("clobTokenIds", "")
        if isinstance(clob_ids, str):
            try:
                clob_ids = json.loads(clob_ids)
            except (json.JSONDecodeError, TypeError):
                clob_ids = [t.strip() for t in clob_ids.split(",") if t.strip()]

        if not clob_ids:
            return None

        # Skip if closed or inactive
        if raw.get("closed") or not raw.get("active", True):
            return None

        # Determine market type
        outcomes = raw.get("outcomes", "")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except:
                outcomes = []

        # Create tokens
        tokens = []
        if len(clob_ids) == 2:
            # Binary market (YES/NO)
            tokens = [
                Token(token_id=clob_ids[0], outcome="YES"),
                Token(token_id=clob_ids[1], outcome="NO"),
            ]
            market_type = MarketType.BINARY
        elif len(clob_ids) > 2:
            # Multi-outcome (NegRisk)
            for i, tid in enumerate(clob_ids):
                outcome_name = outcomes[i] if i < len(outcomes) else f"Outcome_{i}"
                tokens.append(Token(token_id=tid, outcome=outcome_name))
            market_type = MarketType.NEGRISK
        else:
            return None

        # Extract category from tags or group
        category = ""
        tags = raw.get("tags", [])
        if isinstance(tags, list) and tags:
            category = tags[0].lower() if tags else ""
        group_slug = raw.get("groupItemTitle", "") or raw.get("slug", "")
        if "nfl" in group_slug.lower() or "nba" in group_slug.lower():
            category = "sports"
        elif "election" in group_slug.lower() or "president" in group_slug.lower():
            category = "politics"

        return Market(
            market_id=str(raw.get("id", "")),
            condition_id=raw.get("conditionId", ""),
            question=raw.get("question", "Unknown"),
            slug=raw.get("slug", ""),
            tokens=tokens,
            liquidity=float(raw.get("liquidityNum", 0) or 0),
            volume=float(raw.get("volumeNum", 0) or 0),
            category=category,
            market_type=market_type,
            active=raw.get("active", True),
            closed=raw.get("closed", False),
            neg_risk=raw.get("negRisk", False) or len(clob_ids) > 2,
        )

    async def get_all_markets(self, limit: int = 500) -> List[Market]:
        """Fetch and parse all active markets"""
        raw_markets = await self.fetch_markets(limit=limit)
        markets = []

        for raw in raw_markets:
            market = self.parse_market(raw)
            if market:
                markets.append(market)

        return markets

    async def get_binary_markets(self, limit: int = 500) -> List[Market]:
        """Get only binary (YES/NO) markets"""
        markets = await self.get_all_markets(limit)
        return [m for m in markets if m.market_type == MarketType.BINARY]

    async def get_negrisk_markets(self, limit: int = 500) -> List[Market]:
        """Get only NegRisk (multi-outcome) markets"""
        markets = await self.get_all_markets(limit)
        return [m for m in markets if m.market_type == MarketType.NEGRISK]

    async def get_negrisk_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get events with multiple markets (NegRisk structure).

        Polymarket implements NegRisk as separate markets under one event.
        E.g., "Who will win the election?" has 10 candidate markets.
        Each has YES/NO, but all YES should sum to ~$1.
        """
        events = await self.fetch_events(limit=limit)

        negrisk_events = []
        for event in events:
            markets = event.get("markets", [])
            # Event with multiple markets = NegRisk structure
            if len(markets) >= 3:
                # Parse each market
                parsed_markets = []
                for m in markets:
                    parsed = self.parse_market(m)
                    if parsed and parsed.market_type == MarketType.BINARY:
                        parsed_markets.append(parsed)

                if len(parsed_markets) >= 3:
                    negrisk_events.append({
                        "event_id": event.get("id"),
                        "title": event.get("title", ""),
                        "slug": event.get("slug", ""),
                        "markets": parsed_markets,
                        "total_liquidity": sum(m.liquidity for m in parsed_markets),
                    })

        return negrisk_events
