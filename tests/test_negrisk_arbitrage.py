"""
Tests for NegRisk Arbitrage Strategy.

Core business logic:
- Input: Event with multiple markets (candidates), each with YES/NO tokens
- Output: ArbitrageOpportunity if sum(all YES) < $1, else None

NegRisk Arbitrage (Paper: $29M extracted):
- Multiple outcomes under one event (e.g., "Who wins election?")
- Exactly ONE YES resolves to $1.00, all others to $0
- If sum of all YES asks < $1.00, buying all YES guarantees profit
"""
import pytest
import asyncio

import sys
sys.path.insert(0, "src")

from polyarb.strategies.negrisk_arb import NegRiskArbitrageStrategy
from polyarb.models import Market, Token, MarketType, ArbitrageType


class TestNegRiskArbitrageDetection:
    """Core NegRisk arbitrage detection logic"""

    @pytest.mark.asyncio
    async def test_detects_underpriced_yes_arbitrage(
        self, negrisk_event_with_arbitrage, mock_clob_negrisk_arbitrage
    ):
        """
        GIVEN: Event with 5 candidates, sum(YES) = $0.88
        WHEN: Strategy analyzes the event
        THEN: Returns opportunity with ~13.6% profit
        """
        strategy = NegRiskArbitrageStrategy(
            mock_clob_negrisk_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze_event(negrisk_event_with_arbitrage)

        assert result is not None
        assert result.arb_type == ArbitrageType.NEGRISK_UNDERPRICED
        assert result.market_type == MarketType.NEGRISK
        # Sum = 0.20 + 0.18 + 0.17 + 0.16 + 0.17 = 0.88
        assert result.total_cost == pytest.approx(0.88, abs=0.01)
        assert result.profit == pytest.approx(0.12, abs=0.01)
        # profit_percent = (0.12 / 0.88) * 100 = 13.64%
        assert result.profit_percent == pytest.approx(13.64, abs=0.5)

    @pytest.mark.asyncio
    async def test_no_arbitrage_when_sum_over_one(
        self, negrisk_event_no_arbitrage, mock_clob_negrisk_no_arbitrage
    ):
        """
        GIVEN: Event with 4 teams, sum(YES) = $1.05
        WHEN: Strategy analyzes the event
        THEN: Returns None (no underpriced opportunity)
        """
        strategy = NegRiskArbitrageStrategy(
            mock_clob_negrisk_no_arbitrage,
            min_profit_percent=1.0,
            min_liquidity=100,
        )

        result = await strategy.analyze_event(negrisk_event_no_arbitrage)

        # sum = 0.28 + 0.27 + 0.26 + 0.24 = 1.05 > 1.0
        # Should be None for underpriced, but may return overpriced
        # In this case, NO prices would need to be < (N-1) = 3
        assert result is None or result.arb_type == ArbitrageType.NEGRISK_OVERPRICED


class TestNegRiskMath:
    """Tests for the mathematical correctness of NegRisk calculations"""

    @pytest.mark.asyncio
    async def test_profit_calculation_with_five_outcomes(
        self, mock_clob_negrisk_arbitrage
    ):
        """
        5 candidates with YES prices: $0.20, $0.18, $0.17, $0.16, $0.17
        Total = $0.88
        Profit = $1.00 - $0.88 = $0.12
        Profit% = (0.12 / 0.88) * 100 = 13.64%
        """
        from tests.conftest import MockCLOBClient

        markets = [
            Market(
                market_id=f"0xm{i}",
                condition_id=f"c{i}",
                question=f"Will Candidate {chr(65+i)} win?",
                slug=f"cand-{i}",
                tokens=[
                    Token(token_id=f"yes_{i}", outcome="YES"),
                    Token(token_id=f"no_{i}", outcome="NO"),
                ],
                liquidity=20000,
                market_type=MarketType.BINARY,
            )
            for i in range(5)
        ]

        # Prices that sum to 0.88
        clob = MockCLOBClient({
            "yes_0": 0.20,
            "yes_1": 0.18,
            "yes_2": 0.17,
            "yes_3": 0.16,
            "yes_4": 0.17,
        })

        event = {
            "event_id": "event1",
            "title": "Test Election",
            "slug": "test-election",
            "markets": markets,
            "total_liquidity": 100000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        assert result is not None
        assert result.total_cost == pytest.approx(0.88, abs=0.001)
        assert result.profit == pytest.approx(0.12, abs=0.001)
        assert result.profit_percent == pytest.approx(13.636, abs=0.1)

    @pytest.mark.asyncio
    async def test_exactly_one_dollar_sum(self):
        """
        Edge case: sum(YES) = exactly $1.00
        Should NOT return arbitrage (no profit)
        """
        from tests.conftest import MockCLOBClient

        markets = [
            Market(
                market_id=f"0xm{i}",
                condition_id=f"c{i}",
                question=f"Q{i}",
                slug=f"q{i}",
                tokens=[
                    Token(token_id=f"yes_{i}", outcome="YES"),
                    Token(token_id=f"no_{i}", outcome="NO"),
                ],
                liquidity=20000,
                market_type=MarketType.BINARY,
            )
            for i in range(4)
        ]

        # Exactly $1.00
        clob = MockCLOBClient({
            "yes_0": 0.25,
            "yes_1": 0.25,
            "yes_2": 0.25,
            "yes_3": 0.25,
        })

        event = {
            "event_id": "exact",
            "title": "Exact One",
            "slug": "exact",
            "markets": markets,
            "total_liquidity": 80000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        assert result is None


class TestNegRiskEdgeCases:
    """Edge cases for NegRisk strategy"""

    @pytest.mark.asyncio
    async def test_rejects_event_with_fewer_than_3_markets(self):
        """
        GIVEN: Event with only 2 markets
        WHEN: Strategy analyzes
        THEN: Returns None (needs 3+ for NegRisk)
        """
        from tests.conftest import MockCLOBClient

        markets = [
            Market(
                market_id="m1",
                condition_id="c1",
                question="Q1",
                slug="q1",
                tokens=[Token(token_id="y1", outcome="YES"), Token(token_id="n1", outcome="NO")],
                liquidity=10000,
                market_type=MarketType.BINARY,
            ),
            Market(
                market_id="m2",
                condition_id="c2",
                question="Q2",
                slug="q2",
                tokens=[Token(token_id="y2", outcome="YES"), Token(token_id="n2", outcome="NO")],
                liquidity=10000,
                market_type=MarketType.BINARY,
            ),
        ]

        clob = MockCLOBClient({"y1": 0.40, "y2": 0.40})
        event = {"event_id": "e", "markets": markets, "total_liquidity": 20000}

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_missing_prices(self):
        """
        GIVEN: Some YES tokens have no price (API failure)
        WHEN: Strategy analyzes
        THEN: Still calculates with available prices if 3+ valid
        """
        from tests.conftest import MockCLOBClient

        markets = [
            Market(
                market_id=f"m{i}",
                condition_id=f"c{i}",
                question=f"Q{i}",
                slug=f"q{i}",
                tokens=[Token(token_id=f"y{i}", outcome="YES"), Token(token_id=f"n{i}", outcome="NO")],
                liquidity=10000,
                market_type=MarketType.BINARY,
            )
            for i in range(5)
        ]

        # Only 3 prices available
        clob = MockCLOBClient({
            "y0": 0.20,
            "y1": 0.20,
            "y2": 0.20,
            # y3 and y4 missing
        })

        event = {
            "event_id": "partial",
            "title": "Partial",
            "slug": "partial",
            "markets": markets,
            "total_liquidity": 50000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        # 3 valid tokens with sum = 0.60 < 1.0 → should find opportunity
        assert result is not None
        assert result.total_cost == pytest.approx(0.60, abs=0.01)
        assert len(result.tokens) == 3

    @pytest.mark.asyncio
    async def test_handles_zero_prices(self):
        """
        GIVEN: Some YES tokens have price = 0
        WHEN: Strategy analyzes
        THEN: Skips zero prices, uses valid ones
        """
        from tests.conftest import MockCLOBClient

        markets = [
            Market(
                market_id=f"m{i}",
                condition_id=f"c{i}",
                question=f"Q{i}",
                slug=f"q{i}",
                tokens=[Token(token_id=f"y{i}", outcome="YES"), Token(token_id=f"n{i}", outcome="NO")],
                liquidity=10000,
                market_type=MarketType.BINARY,
            )
            for i in range(4)
        ]

        clob = MockCLOBClient({
            "y0": 0.30,
            "y1": 0.0,   # Invalid
            "y2": 0.25,
            "y3": 0.25,
        })

        event = {
            "event_id": "zeros",
            "title": "Zeros",
            "slug": "zeros",
            "markets": markets,
            "total_liquidity": 40000,
        }

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        # 3 valid: 0.30 + 0.25 + 0.25 = 0.80
        assert result is not None
        assert result.total_cost == pytest.approx(0.80, abs=0.01)
        assert len(result.tokens) == 3

    @pytest.mark.asyncio
    async def test_handles_empty_event(self):
        """
        GIVEN: Event with no markets
        WHEN: Strategy analyzes
        THEN: Returns None
        """
        from tests.conftest import MockCLOBClient

        clob = MockCLOBClient({})
        event = {"event_id": "empty", "markets": [], "total_liquidity": 0}

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(event)

        assert result is None


class TestNegRiskThresholds:
    """Tests for threshold filtering in NegRisk"""

    @pytest.mark.asyncio
    async def test_filters_by_min_profit(self, negrisk_event_with_arbitrage):
        """
        GIVEN: Opportunity with ~13.6% profit
        WHEN: min_profit_percent is 20%
        THEN: Returns None
        """
        from tests.conftest import MockCLOBClient

        clob = MockCLOBClient({
            "yes_cand_0": 0.20,
            "yes_cand_1": 0.18,
            "yes_cand_2": 0.17,
            "yes_cand_3": 0.16,
            "yes_cand_4": 0.17,
        })

        strategy = NegRiskArbitrageStrategy(
            clob,
            min_profit_percent=20.0,  # Higher than 13.6%
            min_liquidity=100,
        )

        result = await strategy.analyze_event(negrisk_event_with_arbitrage)

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_min_liquidity(self, negrisk_event_with_arbitrage):
        """
        GIVEN: Event with $100,000 liquidity
        WHEN: min_liquidity is $200,000
        THEN: Returns None
        """
        from tests.conftest import MockCLOBClient

        clob = MockCLOBClient({
            "yes_cand_0": 0.20,
            "yes_cand_1": 0.18,
            "yes_cand_2": 0.17,
            "yes_cand_3": 0.16,
            "yes_cand_4": 0.17,
        })

        strategy = NegRiskArbitrageStrategy(
            clob,
            min_profit_percent=1.0,
            min_liquidity=200000,  # Higher than $100,000
        )

        result = await strategy.analyze_event(negrisk_event_with_arbitrage)

        assert result is None


class TestNegRiskBatchAnalysis:
    """Tests for batch event analysis"""

    @pytest.mark.asyncio
    async def test_batch_analyzes_multiple_events(self):
        """
        GIVEN: Multiple NegRisk events
        WHEN: Strategy batch-analyzes
        THEN: Returns opportunities for valid events only
        """
        from tests.conftest import MockCLOBClient

        # Event 1: Has arbitrage
        event1_markets = [
            Market(
                market_id=f"e1m{i}",
                condition_id=f"e1c{i}",
                question=f"E1Q{i}",
                slug=f"e1q{i}",
                tokens=[Token(token_id=f"e1y{i}", outcome="YES"), Token(token_id=f"e1n{i}", outcome="NO")],
                liquidity=20000,
                market_type=MarketType.BINARY,
            )
            for i in range(4)
        ]
        event1 = {
            "event_id": "event1",
            "title": "Event 1",
            "slug": "event1",
            "markets": event1_markets,
            "total_liquidity": 80000,
        }

        # Event 2: No arbitrage
        event2_markets = [
            Market(
                market_id=f"e2m{i}",
                condition_id=f"e2c{i}",
                question=f"E2Q{i}",
                slug=f"e2q{i}",
                tokens=[Token(token_id=f"e2y{i}", outcome="YES"), Token(token_id=f"e2n{i}", outcome="NO")],
                liquidity=20000,
                market_type=MarketType.BINARY,
            )
            for i in range(3)
        ]
        event2 = {
            "event_id": "event2",
            "title": "Event 2",
            "slug": "event2",
            "markets": event2_markets,
            "total_liquidity": 60000,
        }

        clob = MockCLOBClient({
            # Event 1: sum = 0.80 (arbitrage)
            "e1y0": 0.20, "e1y1": 0.20, "e1y2": 0.20, "e1y3": 0.20,
            # Event 2: sum = 1.05 (no arbitrage)
            "e2y0": 0.35, "e2y1": 0.35, "e2y2": 0.35,
        })

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        results = await strategy.analyze_events_batch([event1, event2])

        assert len(results) == 1
        assert results[0].market_id == "event1"

    @pytest.mark.asyncio
    async def test_batch_returns_sorted_by_profit(self):
        """
        GIVEN: Multiple events with arbitrage
        WHEN: Strategy batch-analyzes
        THEN: Results sorted by profit_percent descending
        """
        from tests.conftest import MockCLOBClient

        def create_event(eid, num_markets):
            markets = [
                Market(
                    market_id=f"{eid}m{i}",
                    condition_id=f"{eid}c{i}",
                    question=f"{eid}Q{i}",
                    slug=f"{eid}q{i}",
                    tokens=[Token(token_id=f"{eid}y{i}", outcome="YES"), Token(token_id=f"{eid}n{i}", outcome="NO")],
                    liquidity=20000,
                    market_type=MarketType.BINARY,
                )
                for i in range(num_markets)
            ]
            return {
                "event_id": eid,
                "title": f"Event {eid}",
                "slug": eid,
                "markets": markets,
                "total_liquidity": num_markets * 20000,
            }

        event_high = create_event("high", 5)  # Will have higher profit
        event_low = create_event("low", 4)    # Will have lower profit

        clob = MockCLOBClient({
            # High: sum = 0.60 → profit 66.67%
            "highy0": 0.12, "highy1": 0.12, "highy2": 0.12, "highy3": 0.12, "highy4": 0.12,
            # Low: sum = 0.80 → profit 25%
            "lowy0": 0.20, "lowy1": 0.20, "lowy2": 0.20, "lowy3": 0.20,
        })

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        results = await strategy.analyze_events_batch([event_low, event_high])

        assert len(results) == 2
        assert results[0].market_id == "high"  # Higher profit first
        assert results[1].market_id == "low"
        assert results[0].profit_percent > results[1].profit_percent


class TestNegRiskOpportunityDetails:
    """Tests for opportunity details in NegRisk"""

    @pytest.mark.asyncio
    async def test_tokens_have_correct_prices(self, negrisk_event_with_arbitrage):
        """
        GIVEN: Event with 5 candidates
        WHEN: Arbitrage detected
        THEN: All tokens have their prices set
        """
        from tests.conftest import MockCLOBClient

        clob = MockCLOBClient({
            "yes_cand_0": 0.20,
            "yes_cand_1": 0.18,
            "yes_cand_2": 0.17,
            "yes_cand_3": 0.16,
            "yes_cand_4": 0.17,
        })

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(negrisk_event_with_arbitrage)

        assert result is not None
        assert len(result.tokens) == 5

        prices = [t.price for t in result.tokens]
        assert 0.20 in prices
        assert 0.18 in prices
        assert 0.17 in prices
        assert 0.16 in prices

    @pytest.mark.asyncio
    async def test_event_metadata_preserved(self, negrisk_event_with_arbitrage):
        """
        GIVEN: Event with specific metadata
        WHEN: Arbitrage detected
        THEN: Opportunity has correct metadata
        """
        from tests.conftest import MockCLOBClient

        clob = MockCLOBClient({
            "yes_cand_0": 0.20,
            "yes_cand_1": 0.18,
            "yes_cand_2": 0.17,
            "yes_cand_3": 0.16,
            "yes_cand_4": 0.17,
        })

        strategy = NegRiskArbitrageStrategy(clob, min_profit_percent=1.0, min_liquidity=100)
        result = await strategy.analyze_event(negrisk_event_with_arbitrage)

        assert result is not None
        assert result.market_id == "0xevent_election"
        assert "[NegRisk]" in result.question
        assert "2024 election" in result.question.lower()
        assert result.url == "https://polymarket.com/event/2024-election-winner"
        assert result.liquidity == 100000
