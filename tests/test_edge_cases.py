"""
Edge Case Tests for Polymarket Arbitrage Bot.

These tests cover extreme, boundary, and unusual scenarios
that could occur in real trading conditions.

Critical edge cases for a trading system:
1. Floating point precision issues
2. Boundary conditions ($1.00 exactly, $0.999999, etc.)
3. Extreme values (very small/large profits)
4. Concurrent access patterns
5. Malformed/unexpected data
"""
import pytest
import asyncio
import math

import sys
sys.path.insert(0, "src")

from polyarb.models import (
    Market, Token, MarketType, OrderBook, OrderBookLevel,
    ArbitrageOpportunity, ArbitrageType, ScanResult
)
from polyarb.strategies.binary_arb import BinaryArbitrageStrategy
from polyarb.strategies.negrisk_arb import NegRiskArbitrageStrategy
from tests.conftest import MockCLOBClient


class TestFloatingPointPrecision:
    """
    Critical: Trading systems must handle floating point correctly.
    $0.01 error on $1M volume = $10,000 loss
    """

    @pytest.mark.asyncio
    async def test_binary_near_boundary_below(self):
        """
        sum = $0.99 (clearly under $1)
        Should detect arbitrage with meaningful profit
        """
        market = Market(
            market_id="precision",
            condition_id="c",
            question="Precision test",
            slug="precision",
            tokens=[
                Token(token_id="yes_prec", outcome="YES"),
                Token(token_id="no_prec", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        # 0.49 + 0.50 = 0.99 → 1.01% profit
        clob = MockCLOBClient({
            "yes_prec": 0.49,
            "no_prec": 0.50,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=0.5, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.profit > 0
        assert result.total_cost < 1.0
        assert result.profit_percent > 1.0  # ~1.01%

    @pytest.mark.asyncio
    async def test_binary_near_boundary_above(self):
        """
        sum = $1.0000001 (just over $1)
        Should NOT detect arbitrage
        """
        market = Market(
            market_id="over",
            condition_id="c",
            question="Over test",
            slug="over",
            tokens=[
                Token(token_id="yes_over", outcome="YES"),
                Token(token_id="no_over", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        clob = MockCLOBClient({
            "yes_over": 0.5000001,
            "no_over": 0.5,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=0.0001, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is None

    def test_order_book_execution_price_precision(self):
        """
        Order book with prices requiring high precision
        """
        book = OrderBook(
            token_id="prec",
            bids=[],
            asks=[
                OrderBookLevel(price=0.123456789, size=100),
                OrderBookLevel(price=0.123456790, size=100),
            ],
        )

        exec_price = book.get_executable_price("buy", 150)

        expected = (100 * 0.123456789 + 50 * 0.123456790) / 150
        assert exec_price == pytest.approx(expected, abs=1e-9)

    def test_profit_calculation_precision(self):
        """
        Profit percent calculation with high precision
        """
        opp = ArbitrageOpportunity(
            market_id="prec",
            condition_id="c",
            question="Precision",
            url="",
            category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.9876543210,
            profit=0.0123456790,
            profit_percent=(0.0123456790 / 0.9876543210) * 100,
            tokens=[],
            liquidity=10000,
        )

        # Verify calculation
        expected_percent = (0.0123456790 / 0.9876543210) * 100
        assert opp.profit_percent == pytest.approx(expected_percent, abs=1e-6)

        # Verify expected profit on investment
        investment = 10000
        expected_profit = investment * (expected_percent / 100)
        assert opp.expected_profit(investment) == pytest.approx(expected_profit, abs=0.01)


class TestExtremeValues:
    """Tests for extreme input values"""

    @pytest.mark.asyncio
    async def test_very_small_profit_margin(self):
        """
        0.1% profit margin (below typical threshold but valid)
        """
        market = Market(
            market_id="tiny",
            condition_id="c",
            question="Tiny margin",
            slug="tiny",
            tokens=[
                Token(token_id="yes_tiny", outcome="YES"),
                Token(token_id="no_tiny", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        clob = MockCLOBClient({
            "yes_tiny": 0.499,  # Total = 0.999, profit = 0.1%
            "no_tiny": 0.500,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=0.05, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.profit_percent == pytest.approx(0.1, abs=0.05)

    @pytest.mark.asyncio
    async def test_very_large_profit_margin(self):
        """
        100%+ profit margin (extremely rare but possible)
        """
        market = Market(
            market_id="huge",
            condition_id="c",
            question="Huge margin",
            slug="huge",
            tokens=[
                Token(token_id="yes_huge", outcome="YES"),
                Token(token_id="no_huge", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        clob = MockCLOBClient({
            "yes_huge": 0.20,  # Total = 0.45, profit = 122%
            "no_huge": 0.25,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.profit_percent > 100

    @pytest.mark.asyncio
    async def test_negrisk_many_outcomes(self):
        """
        NegRisk with 20 outcomes (e.g., "Which state flips?")
        """
        markets = [
            Market(
                market_id=f"m{i}",
                condition_id=f"c{i}",
                question=f"State {i}",
                slug=f"state{i}",
                tokens=[
                    Token(token_id=f"y{i}", outcome="YES"),
                    Token(token_id=f"n{i}", outcome="NO"),
                ],
                liquidity=5000,
                market_type=MarketType.BINARY,
            )
            for i in range(20)
        ]

        # Each YES = 0.04, sum = 0.80 < 1.0
        prices = {f"y{i}": 0.04 for i in range(20)}
        clob = MockCLOBClient(prices)

        event = {
            "event_id": "many",
            "title": "Many outcomes",
            "slug": "many",
            "markets": markets,
            "total_liquidity": 100000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        assert result is not None
        assert result.total_cost == pytest.approx(0.80, abs=0.01)
        assert len(result.tokens) == 20

    def test_very_large_order_book(self):
        """
        Order book with 1000 levels
        """
        asks = [
            OrderBookLevel(price=0.50 + i * 0.001, size=100)
            for i in range(1000)
        ]
        book = OrderBook(token_id="large", bids=[], asks=asks)

        # Execute across many levels
        exec_price = book.get_executable_price("buy", 50000)

        assert exec_price is not None
        assert exec_price > 0.50  # Higher than best ask due to depth

    def test_zero_liquidity_market(self):
        """
        Market with zero liquidity (should still be analyzable)
        """
        market = Market(
            market_id="zero",
            condition_id="c",
            question="Zero liquidity",
            slug="zero",
            tokens=[],
            liquidity=0,
            market_type=MarketType.BINARY,
        )

        assert market.liquidity == 0
        assert market.is_binary is False  # No tokens


class TestMalformedData:
    """Tests for handling unexpected/malformed data"""

    @pytest.mark.asyncio
    async def test_negative_prices(self):
        """
        Negative prices (should never happen but handle gracefully)
        """
        market = Market(
            market_id="neg",
            condition_id="c",
            question="Negative",
            slug="neg",
            tokens=[
                Token(token_id="yes_neg", outcome="YES"),
                Token(token_id="no_neg", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        clob = MockCLOBClient({
            "yes_neg": -0.50,  # Invalid negative price
            "no_neg": 0.50,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze(market)

        # Should handle gracefully (return None or filter out)
        assert result is None

    @pytest.mark.asyncio
    async def test_prices_over_one(self):
        """
        Individual price > $1 (possible in some edge cases)
        """
        market = Market(
            market_id="over1",
            condition_id="c",
            question="Over 1",
            slug="over1",
            tokens=[
                Token(token_id="yes_over1", outcome="YES"),
                Token(token_id="no_over1", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        clob = MockCLOBClient({
            "yes_over1": 1.05,  # Over $1
            "no_over1": 0.02,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze(market)

        # Total = 1.07 > 1.0, no arbitrage
        assert result is None

    @pytest.mark.asyncio
    async def test_negrisk_with_empty_token_list(self):
        """
        Market in event has no tokens
        """
        markets = [
            Market(
                market_id="empty",
                condition_id="c",
                question="Empty tokens",
                slug="empty",
                tokens=[],  # No tokens
                liquidity=10000,
                market_type=MarketType.BINARY,
            ),
            Market(
                market_id="valid1",
                condition_id="c1",
                question="Valid 1",
                slug="v1",
                tokens=[
                    Token(token_id="y1", outcome="YES"),
                    Token(token_id="n1", outcome="NO"),
                ],
                liquidity=10000,
                market_type=MarketType.BINARY,
            ),
            Market(
                market_id="valid2",
                condition_id="c2",
                question="Valid 2",
                slug="v2",
                tokens=[
                    Token(token_id="y2", outcome="YES"),
                    Token(token_id="n2", outcome="NO"),
                ],
                liquidity=10000,
                market_type=MarketType.BINARY,
            ),
            Market(
                market_id="valid3",
                condition_id="c3",
                question="Valid 3",
                slug="v3",
                tokens=[
                    Token(token_id="y3", outcome="YES"),
                    Token(token_id="n3", outcome="NO"),
                ],
                liquidity=10000,
                market_type=MarketType.BINARY,
            ),
        ]

        clob = MockCLOBClient({
            "y1": 0.25,
            "y2": 0.25,
            "y3": 0.25,
        })

        event = {
            "event_id": "partial_empty",
            "title": "Partial Empty",
            "slug": "partial",
            "markets": markets,
            "total_liquidity": 40000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        # Should work with 3 valid markets
        assert result is not None
        assert len(result.tokens) == 3

    def test_order_book_with_nan(self):
        """
        Order book containing NaN values
        """
        book = OrderBook(
            token_id="nan",
            bids=[OrderBookLevel(price=0.45, size=100)],
            asks=[OrderBookLevel(price=float('nan'), size=100)],
        )

        # best_ask will be NaN
        assert math.isnan(book.best_ask)

        # Spread calculation with NaN
        # This could cause issues - let's see how it handles
        spread = book.spread
        assert spread is None or math.isnan(spread)


class TestConcurrencyEdgeCases:
    """Tests for concurrent operations"""

    @pytest.mark.asyncio
    async def test_batch_with_all_failures(self):
        """
        Batch analysis where all API calls fail
        """
        markets = [
            Market(
                market_id=f"fail{i}",
                condition_id=f"c{i}",
                question=f"Fail {i}",
                slug=f"fail{i}",
                tokens=[
                    Token(token_id=f"yes_fail{i}", outcome="YES"),
                    Token(token_id=f"no_fail{i}", outcome="NO"),
                ],
                liquidity=50000,
                market_type=MarketType.BINARY,
            )
            for i in range(5)
        ]

        # All prices missing (simulates API failure)
        clob = MockCLOBClient({})

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        results = await strategy.analyze_batch(markets)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_batch_with_partial_failures(self):
        """
        Batch where some markets fail, others succeed
        """
        markets = [
            Market(
                market_id=f"mix{i}",
                condition_id=f"c{i}",
                question=f"Mix {i}",
                slug=f"mix{i}",
                tokens=[
                    Token(token_id=f"yes_mix{i}", outcome="YES"),
                    Token(token_id=f"no_mix{i}", outcome="NO"),
                ],
                liquidity=50000,
                market_type=MarketType.BINARY,
            )
            for i in range(3)
        ]

        # Only first market has prices
        clob = MockCLOBClient({
            "yes_mix0": 0.45,
            "no_mix0": 0.48,
            # mix1 and mix2 missing
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        results = await strategy.analyze_batch(markets)

        assert len(results) == 1
        assert results[0].market_id == "mix0"

    @pytest.mark.asyncio
    async def test_large_batch_performance(self):
        """
        Batch with 100 markets (performance sanity check)
        """
        markets = [
            Market(
                market_id=f"perf{i}",
                condition_id=f"c{i}",
                question=f"Perf {i}",
                slug=f"perf{i}",
                tokens=[
                    Token(token_id=f"yes_perf{i}", outcome="YES"),
                    Token(token_id=f"no_perf{i}", outcome="NO"),
                ],
                liquidity=50000,
                market_type=MarketType.BINARY,
            )
            for i in range(100)
        ]

        # Half have arbitrage
        prices = {}
        for i in range(100):
            if i % 2 == 0:
                prices[f"yes_perf{i}"] = 0.45  # Arbitrage
                prices[f"no_perf{i}"] = 0.48
            else:
                prices[f"yes_perf{i}"] = 0.52  # No arbitrage
                prices[f"no_perf{i}"] = 0.50

        clob = MockCLOBClient(prices)

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        results = await strategy.analyze_batch(markets)

        assert len(results) == 50  # Half have arbitrage


class TestBoundaryConditions:
    """Tests for exact boundary values"""

    @pytest.mark.asyncio
    async def test_profit_above_threshold(self):
        """
        Profit clearly above min_profit_percent threshold
        Should be included
        """
        market = Market(
            market_id="above_thresh",
            condition_id="c",
            question="Above threshold",
            slug="above",
            tokens=[
                Token(token_id="yes_above", outcome="YES"),
                Token(token_id="no_above", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        # Total = 0.95 → profit% = 5.26%
        clob = MockCLOBClient({
            "yes_above": 0.47,
            "no_above": 0.48,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=5.0, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.profit_percent >= 5.0

    @pytest.mark.asyncio
    async def test_liquidity_exactly_at_threshold(self):
        """
        Liquidity exactly equals min_liquidity
        Should be included (>= not >)
        """
        market = Market(
            market_id="exact_liq",
            condition_id="c",
            question="Exact liquidity",
            slug="exact_liq",
            tokens=[
                Token(token_id="yes_liq", outcome="YES"),
                Token(token_id="no_liq", outcome="NO"),
            ],
            liquidity=1000.0,  # Exactly threshold
            market_type=MarketType.BINARY,
        )

        clob = MockCLOBClient({
            "yes_liq": 0.45,
            "no_liq": 0.48,
        })

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=1000.0)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.liquidity == pytest.approx(1000.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_negrisk_exactly_three_markets(self):
        """
        Minimum valid NegRisk: exactly 3 markets
        """
        markets = [
            Market(
                market_id=f"min{i}",
                condition_id=f"c{i}",
                question=f"Min {i}",
                slug=f"min{i}",
                tokens=[
                    Token(token_id=f"y{i}", outcome="YES"),
                    Token(token_id=f"n{i}", outcome="NO"),
                ],
                liquidity=10000,
                market_type=MarketType.BINARY,
            )
            for i in range(3)
        ]

        clob = MockCLOBClient({
            "y0": 0.30,
            "y1": 0.30,
            "y2": 0.30,  # Sum = 0.90
        })

        event = {
            "event_id": "min3",
            "title": "Minimum 3",
            "slug": "min3",
            "markets": markets,
            "total_liquidity": 30000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        assert result is not None
        assert len(result.tokens) == 3


class TestScanResultAggregation:
    """Tests for ScanResult edge cases"""

    def test_empty_scan_result(self):
        """Empty scan result properties"""
        result = ScanResult()

        assert result.total_potential_profit == 0
        assert result.best_opportunity is None
        assert result.markets_scanned == 0

    def test_single_opportunity_result(self):
        """Single opportunity result"""
        opp = ArbitrageOpportunity(
            market_id="single",
            condition_id="c",
            question="Single",
            url="",
            category="",
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=0.93,
            profit=0.07,
            profit_percent=7.5,
            tokens=[],
            liquidity=10000,
        )

        result = ScanResult(opportunities=[opp], markets_scanned=1)

        assert result.total_potential_profit == pytest.approx(0.07, abs=0.001)
        assert result.best_opportunity is opp

    def test_all_same_profit_opportunities(self):
        """Multiple opportunities with identical profit"""
        opps = [
            ArbitrageOpportunity(
                market_id=f"same{i}",
                condition_id=f"c{i}",
                question=f"Same {i}",
                url="",
                category="",
                arb_type=ArbitrageType.BINARY_UNDERPRICED,
                market_type=MarketType.BINARY,
                total_cost=0.95,
                profit=0.05,
                profit_percent=5.263,  # All same
                tokens=[],
                liquidity=10000,
            )
            for i in range(5)
        ]

        result = ScanResult(opportunities=opps)

        assert result.total_potential_profit == pytest.approx(0.25, abs=0.001)
        assert result.best_opportunity.profit_percent == pytest.approx(5.263, abs=0.001)
