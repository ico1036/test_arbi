"""
Tests for Binary Arbitrage Strategy.

Core business logic tests:
- Input: Market with YES/NO tokens and their prices
- Output: ArbitrageOpportunity based on:
  1. UNDERPRICED: YES_ask + NO_ask < $1 → Buy both, merge for $1
  2. OVERPRICED:  YES_bid + NO_bid > $1 → Mint for $1, sell both

We test the REAL strategy logic, only mocking external API (CLOB) calls.
"""
import pytest
import asyncio

import sys
sys.path.insert(0, "src")

from polyarb.strategies.binary_arb import BinaryArbitrageStrategy
from polyarb.models import Market, Token, MarketType, ArbitrageType


class TestBinaryArbitrageDetection:
    """Core arbitrage detection logic"""

    @pytest.mark.asyncio
    async def test_detects_arbitrage_when_total_under_one(
        self, binary_market_with_arbitrage, mock_clob_arbitrage
    ):
        """
        GIVEN: Market with YES=$0.45, NO=$0.48 (total=$0.93)
        WHEN: Strategy analyzes the market
        THEN: Returns opportunity with ~7.5% profit
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is not None
        assert result.arb_type == ArbitrageType.BINARY_UNDERPRICED
        assert result.total_cost == pytest.approx(0.93, abs=0.01)
        assert result.profit == pytest.approx(0.07, abs=0.01)
        # profit_percent = (0.07 / 0.93) * 100 = 7.53%
        assert result.profit_percent == pytest.approx(7.53, abs=0.1)

    @pytest.mark.asyncio
    async def test_no_arbitrage_when_total_over_one(
        self, binary_market_no_arbitrage, mock_clob_no_arbitrage
    ):
        """
        GIVEN: Market with YES=$0.52, NO=$0.49 (total=$1.01)
        WHEN: Strategy analyzes the market
        THEN: Returns None (no arbitrage)
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_no_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_no_arbitrage)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_arbitrage_when_total_exactly_one(
        self, binary_market_exact_one, mock_clob_exact_one
    ):
        """
        GIVEN: Market with YES=$0.50, NO=$0.50 (total=$1.00)
        WHEN: Strategy analyzes the market
        THEN: Returns None (no profit margin)
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_exact_one,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_exact_one)

        assert result is None


class TestThresholdFiltering:
    """Tests for profit and liquidity thresholds"""

    @pytest.mark.asyncio
    async def test_filters_by_min_profit(
        self, binary_market_with_arbitrage, mock_clob_arbitrage
    ):
        """
        GIVEN: Opportunity with 7.53% profit
        WHEN: min_profit_percent is set to 10%
        THEN: Returns None (doesn't meet threshold)
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=10.0,  # Higher than actual 7.53%
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_min_liquidity(
        self, binary_market_low_liquidity, mock_clob_arbitrage
    ):
        """
        GIVEN: Market with $50 liquidity
        WHEN: min_liquidity is $1000
        THEN: Returns None (doesn't meet threshold)
        """
        # Add prices for low liquidity market
        mock_clob_arbitrage.price_map["yes_lowliq"] = 0.45
        mock_clob_arbitrage.price_map["no_lowliq"] = 0.48

        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=1000,  # Higher than $50
        )

        result = await strategy.analyze(binary_market_low_liquidity)

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_when_meets_thresholds(
        self, binary_market_with_arbitrage, mock_clob_arbitrage
    ):
        """
        GIVEN: Market with 7.53% profit and $50,000 liquidity
        WHEN: Thresholds are 5% profit and $10,000 liquidity
        THEN: Returns opportunity
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=5.0,
            min_liquidity=10000,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is not None
        assert result.profit_percent > 5.0
        assert result.liquidity >= 10000


class TestEdgeCases:
    """Edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_handles_missing_prices(
        self, binary_market_with_arbitrage, mock_clob_missing_prices
    ):
        """
        GIVEN: API returns price for YES but None for NO
        WHEN: Strategy analyzes
        THEN: Returns None (can't calculate)
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_missing_prices,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_zero_prices(
        self, binary_market_with_arbitrage, mock_clob_zero_prices
    ):
        """
        GIVEN: API returns 0 for YES price
        WHEN: Strategy analyzes
        THEN: Returns None (invalid price)
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_zero_prices,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_non_binary_market(self, mock_clob_arbitrage):
        """
        GIVEN: Market with 3 tokens (not binary)
        WHEN: Strategy analyzes
        THEN: Returns None (wrong market type)
        """
        multi_token_market = Market(
            market_id="multi",
            condition_id="cond",
            question="Who wins?",
            slug="who-wins",
            tokens=[
                Token(token_id="a", outcome="A"),
                Token(token_id="b", outcome="B"),
                Token(token_id="c", outcome="C"),
            ],
            liquidity=50000,
            market_type=MarketType.NEGRISK,  # Not BINARY
        )

        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(multi_token_market)

        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_market_with_wrong_token_count(self, mock_clob_arbitrage):
        """
        GIVEN: Market marked as BINARY but has 1 token
        WHEN: Strategy analyzes
        THEN: Returns None (invalid token count)
        """
        one_token_market = Market(
            market_id="one",
            condition_id="cond",
            question="Invalid",
            slug="invalid",
            tokens=[Token(token_id="only", outcome="YES")],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(one_token_market)

        assert result is None


class TestBatchAnalysis:
    """Tests for batch processing multiple markets"""

    @pytest.mark.asyncio
    async def test_batch_analyzes_multiple_markets(
        self,
        binary_market_with_arbitrage,
        binary_market_no_arbitrage,
        mock_clob_arbitrage,
        mock_clob_no_arbitrage,
    ):
        """
        GIVEN: List of markets (some with arbitrage, some without)
        WHEN: Strategy batch-analyzes
        THEN: Returns only opportunities, sorted by profit
        """
        # Merge price maps
        mock_clob_arbitrage.price_map.update(mock_clob_no_arbitrage.price_map)

        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        markets = [binary_market_with_arbitrage, binary_market_no_arbitrage]
        results = await strategy.analyze_batch(markets)

        assert len(results) == 1
        assert results[0].market_id == binary_market_with_arbitrage.market_id

    @pytest.mark.asyncio
    async def test_batch_returns_sorted_by_profit(self, mock_clob_arbitrage):
        """
        GIVEN: Multiple markets with different profit margins
        WHEN: Strategy batch-analyzes
        THEN: Results are sorted by profit_percent descending
        """
        # Create two markets with different profits
        market_high = Market(
            market_id="high_profit",
            condition_id="c1",
            question="High profit market",
            slug="high",
            tokens=[
                Token(token_id="yes_high", outcome="YES"),
                Token(token_id="no_high", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )
        market_low = Market(
            market_id="low_profit",
            condition_id="c2",
            question="Low profit market",
            slug="low",
            tokens=[
                Token(token_id="yes_low", outcome="YES"),
                Token(token_id="no_low", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        # Set prices
        mock_clob_arbitrage.price_map["yes_high"] = 0.40  # Total 0.80, 25% profit
        mock_clob_arbitrage.price_map["no_high"] = 0.40
        mock_clob_arbitrage.price_map["yes_low"] = 0.47  # Total 0.95, 5% profit
        mock_clob_arbitrage.price_map["no_low"] = 0.48

        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        results = await strategy.analyze_batch([market_low, market_high])

        assert len(results) == 2
        assert results[0].market_id == "high_profit"  # Higher profit first
        assert results[1].market_id == "low_profit"
        assert results[0].profit_percent > results[1].profit_percent

    @pytest.mark.asyncio
    async def test_batch_filters_non_binary_markets(self, mock_clob_arbitrage):
        """
        GIVEN: Mix of binary and non-binary markets
        WHEN: Strategy batch-analyzes
        THEN: Only binary markets are analyzed
        """
        binary_market = Market(
            market_id="binary",
            condition_id="c1",
            question="Binary",
            slug="binary",
            tokens=[
                Token(token_id="yes_bin", outcome="YES"),
                Token(token_id="no_bin", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )
        negrisk_market = Market(
            market_id="negrisk",
            condition_id="c2",
            question="NegRisk",
            slug="negrisk",
            tokens=[
                Token(token_id="a", outcome="A"),
                Token(token_id="b", outcome="B"),
                Token(token_id="c", outcome="C"),
            ],
            liquidity=50000,
            market_type=MarketType.NEGRISK,
        )

        mock_clob_arbitrage.price_map["yes_bin"] = 0.45
        mock_clob_arbitrage.price_map["no_bin"] = 0.48

        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        results = await strategy.analyze_batch([binary_market, negrisk_market])

        assert len(results) == 1
        assert results[0].market_id == "binary"


class TestOpportunityDetails:
    """Tests for opportunity details accuracy"""

    @pytest.mark.asyncio
    async def test_token_prices_are_updated(
        self, binary_market_with_arbitrage, mock_clob_arbitrage
    ):
        """
        GIVEN: Market with tokens
        WHEN: Arbitrage is detected
        THEN: Token objects have updated prices
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is not None
        assert len(result.tokens) == 2
        assert result.tokens[0].price == 0.45
        assert result.tokens[0].best_ask == 0.45
        assert result.tokens[1].price == 0.48
        assert result.tokens[1].best_ask == 0.48

    @pytest.mark.asyncio
    async def test_market_metadata_preserved(
        self, binary_market_with_arbitrage, mock_clob_arbitrage
    ):
        """
        GIVEN: Market with specific metadata
        WHEN: Arbitrage is detected
        THEN: Opportunity preserves all metadata
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_with_arbitrage)

        assert result is not None
        assert result.market_id == binary_market_with_arbitrage.market_id
        assert result.condition_id == binary_market_with_arbitrage.condition_id
        assert result.question == binary_market_with_arbitrage.question
        assert result.url == binary_market_with_arbitrage.url
        assert result.liquidity == binary_market_with_arbitrage.liquidity
        assert result.market_type == MarketType.BINARY


# =============================================================================
# OVERPRICED Arbitrage Tests (Mint & Sell Strategy)
# =============================================================================

class TestOverpricedArbitrageDetection:
    """
    Tests for OVERPRICED arbitrage: YES_bid + NO_bid > $1.00

    Strategy: Mint YES+NO pair for $1, sell both at market bid prices.
    Profit = (YES_bid + NO_bid) - $1.00
    """

    @pytest.mark.asyncio
    async def test_detects_overpriced_when_bids_over_one(
        self, binary_market_for_overpriced, mock_clob_overpriced
    ):
        """
        GIVEN: Market with YES_bid=$0.55, NO_bid=$0.52 (total=$1.07)
        WHEN: Strategy analyzes the market
        THEN: Returns OVERPRICED opportunity with 7% profit
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_overpriced,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_for_overpriced)

        assert result is not None
        assert result.arb_type == ArbitrageType.BINARY_OVERPRICED
        assert result.total_cost == 1.0  # Mint cost is always $1
        assert result.profit == pytest.approx(0.07, abs=0.01)
        assert result.profit_percent == pytest.approx(7.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_overpriced_when_bids_under_one(
        self, binary_market_for_overpriced, mock_clob_no_overpriced
    ):
        """
        GIVEN: Market with YES_bid=$0.48, NO_bid=$0.50 (total=$0.98)
        WHEN: Strategy analyzes the market
        THEN: Returns None (no overpriced opportunity)
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_no_overpriced,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_for_overpriced)

        # No underpriced (ask > $1), no overpriced (bid < $1)
        assert result is None

    @pytest.mark.asyncio
    async def test_overpriced_uses_bid_prices(
        self, binary_market_for_overpriced, mock_clob_overpriced
    ):
        """
        GIVEN: Market with different bid/ask prices
        WHEN: Overpriced opportunity is detected
        THEN: Token prices reflect BID (sell) prices, not ASK
        """
        strategy = BinaryArbitrageStrategy(
            mock_clob_overpriced,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze(binary_market_for_overpriced)

        assert result is not None
        # Bid prices from fixture: YES=$0.55, NO=$0.52
        assert result.tokens[0].best_bid == 0.55
        assert result.tokens[1].best_bid == 0.52

    @pytest.mark.asyncio
    async def test_overpriced_profit_calculation(self):
        """
        Verify overpriced profit math:
        - Mint cost: $1.00 (always)
        - Sell proceeds: YES_bid + NO_bid
        - Profit: proceeds - $1.00
        - Profit %: (profit / $1.00) * 100
        """
        from tests.conftest import MockCLOBClient

        market = Market(
            market_id="math_test",
            condition_id="c",
            question="Math test",
            slug="math",
            tokens=[
                Token(token_id="yes_math", outcome="YES"),
                Token(token_id="no_math", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        # YES bid = 0.60, NO bid = 0.50 → Total = 1.10
        clob = MockCLOBClient(
            price_map={"yes_math": 0.65, "no_math": 0.55},
            bid_map={"yes_math": 0.60, "no_math": 0.50},
        )

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.arb_type == ArbitrageType.BINARY_OVERPRICED
        assert result.total_cost == 1.0
        assert result.profit == pytest.approx(0.10, abs=0.001)  # 1.10 - 1.00
        assert result.profit_percent == pytest.approx(10.0, abs=0.1)  # 10%

    @pytest.mark.asyncio
    async def test_overpriced_threshold_filtering(self):
        """
        GIVEN: Overpriced opportunity with 3% profit
        WHEN: min_profit_percent is 5%
        THEN: Returns None (doesn't meet threshold)
        """
        from tests.conftest import MockCLOBClient

        market = Market(
            market_id="thresh_test",
            condition_id="c",
            question="Threshold test",
            slug="thresh",
            tokens=[
                Token(token_id="yes_th", outcome="YES"),
                Token(token_id="no_th", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        # Total bid = 1.03 → 3% profit
        clob = MockCLOBClient(
            price_map={"yes_th": 0.55, "no_th": 0.52},
            bid_map={"yes_th": 0.52, "no_th": 0.51},
        )

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=5.0, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is None


class TestUnderpriceOverpricePriority:
    """Tests for when both underpriced and overpriced might exist"""

    @pytest.mark.asyncio
    async def test_underpriced_checked_first(self):
        """
        GIVEN: Market where BOTH underpriced and overpriced conditions exist
              (unusual but possible with wide spreads)
        WHEN: Strategy analyzes
        THEN: Underpriced is returned (checked first)
        """
        from tests.conftest import MockCLOBClient

        market = Market(
            market_id="both",
            condition_id="c",
            question="Both conditions",
            slug="both",
            tokens=[
                Token(token_id="yes_both", outcome="YES"),
                Token(token_id="no_both", outcome="NO"),
            ],
            liquidity=50000,
            market_type=MarketType.BINARY,
        )

        # Ask total = 0.90 (underpriced), Bid total = 1.10 (overpriced)
        # This is a wide spread scenario
        clob = MockCLOBClient(
            price_map={"yes_both": 0.45, "no_both": 0.45},  # Ask total = 0.90
            bid_map={"yes_both": 0.55, "no_both": 0.55},    # Bid total = 1.10
        )

        strategy = BinaryArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze(market)

        assert result is not None
        assert result.arb_type == ArbitrageType.BINARY_UNDERPRICED  # Underpriced first
