"""
Tests for data models.

These tests verify that our data models correctly calculate
derived values and handle edge cases.

NO MOCKING - pure unit tests on data structures.
"""
import pytest
from datetime import datetime

import sys
sys.path.insert(0, "src")

from polyarb.models import (
    Token,
    Market,
    MarketType,
    OrderBook,
    OrderBookLevel,
    ArbitrageOpportunity,
    ArbitrageType,
    ScanResult,
)


class TestOrderBookLevel:
    """Tests for OrderBookLevel"""

    def test_value_calculation(self):
        """Level value = price * size"""
        level = OrderBookLevel(price=0.50, size=1000)
        assert level.value == 500.0

    def test_zero_size(self):
        """Zero size gives zero value"""
        level = OrderBookLevel(price=0.50, size=0)
        assert level.value == 0.0

    def test_zero_price(self):
        """Zero price gives zero value"""
        level = OrderBookLevel(price=0.0, size=1000)
        assert level.value == 0.0


class TestOrderBook:
    """Tests for OrderBook"""

    def test_best_bid_ask(self, order_book_with_depth):
        """Best bid/ask from sorted order book"""
        book = order_book_with_depth
        assert book.best_bid == 0.48
        assert book.best_ask == 0.52

    def test_spread_calculation(self, order_book_with_depth):
        """Spread = best_ask - best_bid"""
        book = order_book_with_depth
        assert book.spread == pytest.approx(0.04, abs=0.001)

    def test_empty_order_book(self, order_book_empty):
        """Empty book returns None for prices"""
        book = order_book_empty
        assert book.best_bid is None
        assert book.best_ask is None
        assert book.spread is None

    def test_executable_price_small_order(self, order_book_with_depth):
        """Small order executes at best ask"""
        book = order_book_with_depth
        # 100 shares at $0.52 (first level has 500)
        exec_price = book.get_executable_price("buy", 100)
        assert exec_price == pytest.approx(0.52, abs=0.001)

    def test_executable_price_crosses_levels(self, order_book_with_depth):
        """Large order crosses multiple levels"""
        book = order_book_with_depth
        # 1000 shares: 500 @ 0.52 + 500 @ 0.53 = 525 / 1000 = 0.525
        exec_price = book.get_executable_price("buy", 1000)
        assert exec_price == pytest.approx(0.525, abs=0.001)

    def test_executable_price_insufficient_liquidity(self, order_book_thin):
        """Returns None if not enough liquidity"""
        book = order_book_thin
        # Only 100 available, requesting 1000
        exec_price = book.get_executable_price("buy", 1000)
        assert exec_price is None

    def test_slippage_calculation(self, order_book_with_depth):
        """Slippage increases with order size"""
        book = order_book_with_depth

        # Small order - no slippage
        slippage_small = book.get_slippage("buy", 100)
        assert slippage_small == pytest.approx(0.0, abs=0.01)

        # Large order - some slippage
        slippage_large = book.get_slippage("buy", 1000)
        # (0.525 - 0.52) / 0.52 * 100 = 0.96%
        assert slippage_large == pytest.approx(0.96, abs=0.1)

    def test_slippage_empty_book(self, order_book_empty):
        """Empty book returns None for slippage"""
        assert order_book_empty.get_slippage("buy", 100) is None


class TestMarket:
    """Tests for Market model"""

    def test_binary_market_detection(self, binary_market_with_arbitrage):
        """Binary market has exactly 2 tokens"""
        market = binary_market_with_arbitrage
        assert market.is_binary is True
        assert market.is_multi_outcome is False
        assert len(market.tokens) == 2

    def test_multi_outcome_detection(self):
        """Multi-outcome market has 3+ tokens"""
        market = Market(
            market_id="multi",
            condition_id="cond",
            question="Who wins?",
            slug="who-wins",
            tokens=[
                Token(token_id="a", outcome="A"),
                Token(token_id="b", outcome="B"),
                Token(token_id="c", outcome="C"),
            ],
            liquidity=10000,
        )
        assert market.is_binary is False
        assert market.is_multi_outcome is True

    def test_url_generation(self, binary_market_with_arbitrage):
        """URL is correctly generated from slug"""
        market = binary_market_with_arbitrage
        assert market.url == "https://polymarket.com/event/will-btc-100k-2024"

    def test_url_empty_slug(self):
        """Empty slug gives empty URL"""
        market = Market(
            market_id="x",
            condition_id="c",
            question="Q",
            slug="",
            tokens=[],
            liquidity=0,
        )
        assert market.url == ""


class TestArbitrageOpportunity:
    """Tests for ArbitrageOpportunity model"""

    def test_expected_profit_calculation(self):
        """Expected profit = investment * profit_percent / 100"""
        opp = ArbitrageOpportunity(
            market_id="test",
            condition_id="cond",
            question="Test",
            url="https://test.com",
            category="test",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.93,
            profit=0.07,
            profit_percent=7.53,  # (0.07 / 0.93) * 100
            tokens=[],
            liquidity=10000,
        )

        # $1000 investment at 7.53% = $75.30 profit
        assert opp.expected_profit(1000) == pytest.approx(75.3, abs=0.1)

    def test_key_uniqueness(self):
        """Key combines market_id and profit_percent"""
        opp = ArbitrageOpportunity(
            market_id="0xabc",
            condition_id="cond",
            question="Test",
            url="",
            category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.93,
            profit=0.07,
            profit_percent=7.53,
            tokens=[],
            liquidity=10000,
        )
        assert opp.key == "0xabc_7.53"

    def test_to_dict_conversion(self):
        """to_dict returns serializable dictionary"""
        opp = ArbitrageOpportunity(
            market_id="0xtest",
            condition_id="cond",
            question="A very long question that exceeds 100 characters " * 3,
            url="https://test.com",
            category="crypto",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.93,
            profit=0.07,
            profit_percent=7.53,
            tokens=[],
            liquidity=50000,
            max_executable_size=1000,
        )

        d = opp.to_dict()

        assert d["market_id"] == "0xtest"
        assert d["arb_type"] == "binary_underpriced"
        assert d["market_type"] == "binary"
        assert d["profit_percent"] == 7.53
        assert len(d["question"]) == 100  # Truncated


class TestScanResult:
    """Tests for ScanResult model"""

    def test_total_potential_profit(self):
        """Sum of all opportunity profits"""
        opp1 = ArbitrageOpportunity(
            market_id="1", condition_id="c1", question="Q1", url="", category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.93, profit=0.07, profit_percent=7.5,
            tokens=[], liquidity=10000,
        )
        opp2 = ArbitrageOpportunity(
            market_id="2", condition_id="c2", question="Q2", url="", category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.95, profit=0.05, profit_percent=5.3,
            tokens=[], liquidity=10000,
        )

        result = ScanResult(
            opportunities=[opp1, opp2],
            markets_scanned=100,
        )

        assert result.total_potential_profit == pytest.approx(0.12, abs=0.001)

    def test_best_opportunity(self):
        """Returns opportunity with highest profit_percent"""
        opp_low = ArbitrageOpportunity(
            market_id="low", condition_id="c", question="Q", url="", category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.97, profit=0.03, profit_percent=3.1,
            tokens=[], liquidity=10000,
        )
        opp_high = ArbitrageOpportunity(
            market_id="high", condition_id="c", question="Q", url="", category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.90, profit=0.10, profit_percent=11.1,
            tokens=[], liquidity=10000,
        )

        result = ScanResult(opportunities=[opp_low, opp_high])

        assert result.best_opportunity.market_id == "high"
        assert result.best_opportunity.profit_percent == 11.1

    def test_best_opportunity_empty(self):
        """Empty result returns None for best"""
        result = ScanResult(opportunities=[])
        assert result.best_opportunity is None
