"""
Pytest fixtures for Polymarket Arbitrage Bot tests.
"""
import pytest
import asyncio

import sys
sys.path.insert(0, "src")

from polyarb.models import Market, Token, MarketType, OrderBook, OrderBookLevel


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
# Binary Market Fixtures
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
