"""
Pytest fixtures for Polymarket Arbitrage Bot tests.

These fixtures provide real-like test data without mocking internal logic.
We only mock external API calls (network I/O).
"""
import pytest
import asyncio
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import sys
sys.path.insert(0, "src")

from polyarb.models import Market, Token, MarketType, OrderBook, OrderBookLevel
from polyarb.api.clob import CLOBClient
from polyarb.config import Config, ArbitrageConfig, APIConfig


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """Test configuration with lower thresholds"""
    return Config(
        api=APIConfig(
            gamma_api="https://gamma-api.polymarket.com",
            clob_api="https://clob.polymarket.com",
            max_concurrent=10,
        ),
        arbitrage=ArbitrageConfig(
            min_profit_percent=1.0,
            min_liquidity=100,
            max_markets=100,
        ),
    )


# =============================================================================
# Binary Market Fixtures - Real-like data
# =============================================================================

@pytest.fixture
def binary_market_with_arbitrage() -> Market:
    """
    Binary market with clear arbitrage opportunity.
    YES $0.45 + NO $0.48 = $0.93 → 7.53% profit
    """
    return Market(
        market_id="0xarb123",
        condition_id="cond_arb123",
        question="Will Bitcoin reach $100k by 2024?",
        slug="will-btc-100k-2024",
        tokens=[
            Token(token_id="yes_token_arb", outcome="YES"),
            Token(token_id="no_token_arb", outcome="NO"),
        ],
        liquidity=50000.0,
        volume=100000.0,
        market_type=MarketType.BINARY,
        active=True,
    )


@pytest.fixture
def binary_market_no_arbitrage() -> Market:
    """
    Binary market with no arbitrage (fair pricing).
    YES $0.52 + NO $0.49 = $1.01 → No opportunity
    """
    return Market(
        market_id="0xfair456",
        condition_id="cond_fair456",
        question="Will ETH reach $5k by 2024?",
        slug="will-eth-5k-2024",
        tokens=[
            Token(token_id="yes_token_fair", outcome="YES"),
            Token(token_id="no_token_fair", outcome="NO"),
        ],
        liquidity=30000.0,
        volume=50000.0,
        market_type=MarketType.BINARY,
        active=True,
    )


@pytest.fixture
def binary_market_exact_one() -> Market:
    """
    Binary market with exactly $1.00 total (edge case).
    YES $0.50 + NO $0.50 = $1.00 → No arbitrage
    """
    return Market(
        market_id="0xexact789",
        condition_id="cond_exact789",
        question="Will it rain tomorrow?",
        slug="will-rain-tomorrow",
        tokens=[
            Token(token_id="yes_token_exact", outcome="YES"),
            Token(token_id="no_token_exact", outcome="NO"),
        ],
        liquidity=10000.0,
        market_type=MarketType.BINARY,
    )


@pytest.fixture
def binary_market_low_liquidity() -> Market:
    """
    Binary market with arbitrage but LOW liquidity.
    Should be filtered out by min_liquidity threshold.
    """
    return Market(
        market_id="0xlowliq",
        condition_id="cond_lowliq",
        question="Obscure market with low liquidity",
        slug="low-liq-market",
        tokens=[
            Token(token_id="yes_lowliq", outcome="YES"),
            Token(token_id="no_lowliq", outcome="NO"),
        ],
        liquidity=50.0,  # Very low
        market_type=MarketType.BINARY,
    )


# =============================================================================
# NegRisk Event Fixtures - Multi-outcome markets
# =============================================================================

@pytest.fixture
def negrisk_event_with_arbitrage() -> Dict:
    """
    NegRisk event with 5 candidates.
    Sum of YES = $0.88 → 13.64% profit
    """
    markets = [
        Market(
            market_id=f"0xneg_{i}",
            condition_id=f"cond_neg_{i}",
            question=f"Will Candidate {chr(65+i)} win?",
            slug=f"candidate-{chr(97+i)}-win",
            tokens=[
                Token(token_id=f"yes_cand_{i}", outcome="YES"),
                Token(token_id=f"no_cand_{i}", outcome="NO"),
            ],
            liquidity=20000.0,
            market_type=MarketType.BINARY,
        )
        for i in range(5)
    ]

    return {
        "event_id": "0xevent_election",
        "title": "Who will win the 2024 election?",
        "slug": "2024-election-winner",
        "markets": markets,
        "total_liquidity": 100000.0,
    }


@pytest.fixture
def negrisk_event_no_arbitrage() -> Dict:
    """
    NegRisk event with fair pricing.
    Sum of YES = $1.05 → No underpriced opportunity
    """
    markets = [
        Market(
            market_id=f"0xneg_fair_{i}",
            condition_id=f"cond_neg_fair_{i}",
            question=f"Will Team {chr(65+i)} win championship?",
            slug=f"team-{chr(97+i)}-championship",
            tokens=[
                Token(token_id=f"yes_team_{i}", outcome="YES"),
                Token(token_id=f"no_team_{i}", outcome="NO"),
            ],
            liquidity=15000.0,
            market_type=MarketType.BINARY,
        )
        for i in range(4)
    ]

    return {
        "event_id": "0xevent_sports",
        "title": "Who will win the championship?",
        "slug": "championship-winner",
        "markets": markets,
        "total_liquidity": 60000.0,
    }


# =============================================================================
# Order Book Fixtures
# =============================================================================

@pytest.fixture
def order_book_with_depth() -> OrderBook:
    """Order book with multiple levels for depth analysis"""
    return OrderBook(
        token_id="test_token",
        bids=[
            OrderBookLevel(price=0.48, size=500),
            OrderBookLevel(price=0.47, size=1000),
            OrderBookLevel(price=0.46, size=2000),
        ],
        asks=[
            OrderBookLevel(price=0.52, size=500),
            OrderBookLevel(price=0.53, size=1000),
            OrderBookLevel(price=0.54, size=2000),
        ],
    )


@pytest.fixture
def order_book_thin() -> OrderBook:
    """Thin order book with limited liquidity"""
    return OrderBook(
        token_id="thin_token",
        bids=[OrderBookLevel(price=0.45, size=100)],
        asks=[OrderBookLevel(price=0.55, size=100)],
    )


@pytest.fixture
def order_book_empty() -> OrderBook:
    """Empty order book"""
    return OrderBook(token_id="empty_token", bids=[], asks=[])


# =============================================================================
# Mock CLOB Client - Only mocks network I/O
# =============================================================================

class MockCLOBClient:
    """
    Mock CLOB client that simulates API responses.
    This is the ONLY place we mock - external API calls.

    Supports separate bid/ask prices for overpriced arbitrage testing.
    """

    def __init__(
        self,
        price_map: Dict[str, float],
        bid_map: Optional[Dict[str, float]] = None,
    ):
        """
        Args:
            price_map: Dict mapping token_id -> ask price (for side="buy")
            bid_map: Optional dict mapping token_id -> bid price (for side="sell")
                     If not provided, bid = ask - 0.02 (default spread)
        """
        self.price_map = price_map  # Ask prices
        self.bid_map = bid_map or {}  # Bid prices
        self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get_price(self, token_id: str, side: str = "buy") -> Optional[float]:
        if side == "sell":
            # Return bid price
            if token_id in self.bid_map:
                return self.bid_map.get(token_id)
            # Default: bid = ask - 0.02
            ask = self.price_map.get(token_id)
            return ask - 0.02 if ask else None
        return self.price_map.get(token_id)

    async def get_prices_batch(
        self, token_ids: List[str], side: str = "buy"
    ) -> Dict[str, Optional[float]]:
        return {tid: await self.get_price(tid, side) for tid in token_ids}

    async def get_order_book(self, token_id: str) -> Optional[OrderBook]:
        price = self.price_map.get(token_id)
        if price is None:
            return None
        return OrderBook(
            token_id=token_id,
            bids=[OrderBookLevel(price=price - 0.02, size=1000)],
            asks=[OrderBookLevel(price=price, size=1000)],
        )

    async def analyze_depth(
        self, token_id: str, target_size: float
    ) -> Dict[str, Optional[float]]:
        price = self.price_map.get(token_id)
        if price is None:
            return {"executable_price": None, "slippage_percent": None, "available_size": 0}
        return {
            "executable_price": price,
            "slippage_percent": 0.1,
            "available_size": 5000,
        }


@pytest.fixture
def mock_clob_arbitrage():
    """
    Mock CLOB with prices that create arbitrage.
    YES: $0.45, NO: $0.48 → Total: $0.93
    """
    return MockCLOBClient({
        "yes_token_arb": 0.45,
        "no_token_arb": 0.48,
    })


@pytest.fixture
def mock_clob_no_arbitrage():
    """
    Mock CLOB with fair prices (no arbitrage).
    YES: $0.52, NO: $0.49 → Total: $1.01
    """
    return MockCLOBClient({
        "yes_token_fair": 0.52,
        "no_token_fair": 0.49,
    })


@pytest.fixture
def mock_clob_exact_one():
    """
    Mock CLOB with exactly $1.00 total.
    YES: $0.50, NO: $0.50 → Total: $1.00
    """
    return MockCLOBClient({
        "yes_token_exact": 0.50,
        "no_token_exact": 0.50,
    })


@pytest.fixture
def mock_clob_negrisk_arbitrage():
    """
    Mock CLOB for NegRisk with underpriced YES tokens.
    5 candidates: $0.20, $0.18, $0.17, $0.16, $0.17 = $0.88
    """
    prices = {
        "yes_cand_0": 0.20,
        "yes_cand_1": 0.18,
        "yes_cand_2": 0.17,
        "yes_cand_3": 0.16,
        "yes_cand_4": 0.17,
    }
    # Add NO prices for overpriced check
    for i in range(5):
        prices[f"no_cand_{i}"] = 0.80 + i * 0.01
    return MockCLOBClient(prices)


@pytest.fixture
def mock_clob_negrisk_no_arbitrage():
    """
    Mock CLOB for NegRisk with fair pricing.
    4 teams: $0.28, $0.27, $0.26, $0.24 = $1.05
    """
    return MockCLOBClient({
        "yes_team_0": 0.28,
        "yes_team_1": 0.27,
        "yes_team_2": 0.26,
        "yes_team_3": 0.24,
    })


@pytest.fixture
def mock_clob_missing_prices():
    """Mock CLOB with missing prices (API failure simulation)"""
    return MockCLOBClient({
        "yes_token_arb": 0.45,
        # no_token_arb is missing - simulates API failure
    })


@pytest.fixture
def mock_clob_zero_prices():
    """Mock CLOB with zero prices (invalid data)"""
    return MockCLOBClient({
        "yes_token_arb": 0.0,
        "no_token_arb": 0.48,
    })


# =============================================================================
# Overpriced Arbitrage Fixtures (Mint & Sell strategy)
# =============================================================================

@pytest.fixture
def binary_market_for_overpriced() -> Market:
    """
    Binary market for overpriced testing.
    Uses different token IDs from underpriced fixtures.
    """
    return Market(
        market_id="0xoverpriced",
        condition_id="cond_overpriced",
        question="Will market be overpriced?",
        slug="overpriced-market",
        tokens=[
            Token(token_id="yes_over", outcome="YES"),
            Token(token_id="no_over", outcome="NO"),
        ],
        liquidity=50000.0,
        volume=100000.0,
        market_type=MarketType.BINARY,
        active=True,
    )


@pytest.fixture
def mock_clob_overpriced():
    """
    Mock CLOB with overpriced market.
    YES bid: $0.55, NO bid: $0.52 → Total bid: $1.07
    Profit: $0.07 (7% on $1 mint cost)
    """
    return MockCLOBClient(
        price_map={
            "yes_over": 0.57,  # Ask (not used for overpriced)
            "no_over": 0.54,
        },
        bid_map={
            "yes_over": 0.55,  # Bid - what we get when selling
            "no_over": 0.52,
        },
    )


@pytest.fixture
def mock_clob_no_overpriced():
    """
    Mock CLOB where bid total <= $1 (no overpriced opportunity).
    YES bid: $0.48, NO bid: $0.50 → Total bid: $0.98
    """
    return MockCLOBClient(
        price_map={
            "yes_over": 0.50,
            "no_over": 0.52,
        },
        bid_map={
            "yes_over": 0.48,
            "no_over": 0.50,
        },
    )
