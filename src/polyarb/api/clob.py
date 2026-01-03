"""
CLOB API Client - Order book and pricing data
https://clob.polymarket.com
"""
import asyncio
from typing import List, Optional, Dict, Tuple
import aiohttp

from ..config import config
from ..models import Token, OrderBook, OrderBookLevel


class CLOBClient:
    """Async client for Polymarket CLOB API (order book/pricing)"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or config.api.clob_api
        self.timeout = aiohttp.ClientTimeout(total=10)
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(config.api.max_concurrent)

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

    async def get_price(self, token_id: str, side: str = "buy") -> Optional[float]:
        """
        Get best price for a token.
        side: "buy" for best ask, "sell" for best bid
        """
        async with self._semaphore:
            try:
                async with self.session.get(
                    f"{self.base_url}/price",
                    params={"token_id": token_id, "side": side},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = data.get("price")
                        return float(price) if price else None
            except Exception:
                pass
        return None

    async def get_prices_batch(
        self, token_ids: List[str], side: str = "buy"
    ) -> Dict[str, Optional[float]]:
        """Get prices for multiple tokens concurrently"""
        tasks = [self.get_price(tid, side) for tid in token_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        prices = {}
        for tid, result in zip(token_ids, results):
            if isinstance(result, Exception):
                prices[tid] = None
            else:
                prices[tid] = result

        return prices

    async def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Get full order book for a token"""
        async with self._semaphore:
            try:
                async with self.session.get(
                    f"{self.base_url}/book", params={"token_id": token_id}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_order_book(token_id, data)
            except Exception:
                pass
        return None

    def _parse_order_book(self, token_id: str, data: Dict) -> OrderBook:
        """Parse raw order book data"""
        bids = []
        asks = []

        for bid in data.get("bids", []):
            try:
                bids.append(
                    OrderBookLevel(price=float(bid["price"]), size=float(bid["size"]))
                )
            except (KeyError, ValueError):
                continue

        for ask in data.get("asks", []):
            try:
                asks.append(
                    OrderBookLevel(price=float(ask["price"]), size=float(ask["size"]))
                )
            except (KeyError, ValueError):
                continue

        # Sort: bids descending (best bid first), asks ascending (best ask first)
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)

        return OrderBook(token_id=token_id, bids=bids, asks=asks)

    async def get_order_books_batch(
        self, token_ids: List[str]
    ) -> Dict[str, Optional[OrderBook]]:
        """Get order books for multiple tokens concurrently"""
        tasks = [self.get_order_book(tid) for tid in token_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        books = {}
        for tid, result in zip(token_ids, results):
            if isinstance(result, Exception):
                books[tid] = None
            else:
                books[tid] = result

        return books

    async def get_spread(self, token_id: str) -> Optional[Tuple[float, float, float]]:
        """
        Get bid/ask spread for a token.
        Returns (best_bid, best_ask, spread) or None
        """
        book = await self.get_order_book(token_id)
        if book and book.best_bid and book.best_ask:
            spread = book.best_ask - book.best_bid
            return (book.best_bid, book.best_ask, spread)
        return None

    async def analyze_depth(
        self, token_id: str, target_size: float
    ) -> Dict[str, Optional[float]]:
        """
        Analyze order book depth for execution.
        Returns dict with executable price, slippage, and available size.
        """
        book = await self.get_order_book(token_id)
        if not book:
            return {
                "executable_price": None,
                "slippage_percent": None,
                "available_size": 0,
            }

        # Calculate for buy side (asks)
        exec_price = book.get_executable_price("buy", target_size)
        slippage = book.get_slippage("buy", target_size)

        # Calculate total available liquidity
        available = sum(level.size for level in book.asks)

        return {
            "executable_price": exec_price,
            "slippage_percent": slippage,
            "available_size": available,
            "best_ask": book.best_ask,
            "best_bid": book.best_bid,
        }
