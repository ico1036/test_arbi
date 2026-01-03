"""
Tests for WebSocket-based real-time arbitrage detection.

Tests the RealtimeArbitrageDetector, MarketState, and NegRiskEventState classes.
"""
import pytest
import sys

sys.path.insert(0, "src")

from polyarb.api.websocket import (
    MarketState,
    NegRiskEventState,
    RealtimeArbitrageDetector,
)


# =============================================================================
# MarketState Tests (Binary Markets)
# =============================================================================


class TestMarketState:
    """Tests for MarketState class"""

    def test_underpriced_detection(self):
        """Detect underpriced opportunity when YES_ask + NO_ask < $1"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_ask=0.45,
            no_ask=0.48,
        )

        opp = state.check_underpriced(min_profit=1.0)

        assert opp is not None
        assert opp["type"] == "BINARY_UNDERPRICED"
        assert opp["total_cost"] == pytest.approx(0.93)
        assert opp["profit"] == pytest.approx(0.07)
        assert opp["profit_percent"] == pytest.approx(7.53, rel=0.01)

    def test_no_underpriced_when_fair(self):
        """No opportunity when YES_ask + NO_ask >= $1"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_ask=0.52,
            no_ask=0.49,
        )

        opp = state.check_underpriced(min_profit=1.0)
        assert opp is None

    def test_overpriced_detection(self):
        """Detect overpriced opportunity when YES_bid + NO_bid > $1"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_bid=0.55,
            no_bid=0.52,
        )

        opp = state.check_overpriced(min_profit=1.0)

        assert opp is not None
        assert opp["type"] == "BINARY_OVERPRICED"
        assert opp["total_value"] == pytest.approx(1.07)
        assert opp["profit"] == pytest.approx(0.07)
        assert opp["profit_percent"] == pytest.approx(7.0)

    def test_no_overpriced_when_fair(self):
        """No opportunity when YES_bid + NO_bid <= $1"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_bid=0.48,
            no_bid=0.50,
        )

        opp = state.check_overpriced(min_profit=1.0)
        assert opp is None

    def test_update_price(self):
        """Test price updates via token_id"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
        )

        # Initially no prices
        assert state.yes_ask is None
        assert state.no_ask is None

        # Update YES price
        state.update_price("yes_token", bid=0.43, ask=0.45)
        assert state.yes_ask == 0.45
        assert state.yes_bid == 0.43

        # Update NO price
        state.update_price("no_token", bid=0.46, ask=0.48)
        assert state.no_ask == 0.48
        assert state.no_bid == 0.46

    def test_missing_prices_returns_none(self):
        """No detection when prices are missing"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_ask=0.45,  # Only YES price
        )

        assert state.check_underpriced(min_profit=1.0) is None
        assert state.check_overpriced(min_profit=1.0) is None

    def test_zero_prices_returns_none(self):
        """No detection when prices are zero"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_ask=0.0,
            no_ask=0.48,
        )

        assert state.check_underpriced(min_profit=1.0) is None

    def test_min_profit_threshold(self):
        """Opportunity rejected if below min profit"""
        state = MarketState(
            market_id="test_market",
            question="Test question?",
            slug="test-question",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_token",
            no_token_id="no_token",
            yes_ask=0.49,
            no_ask=0.50,  # Total 0.99, only 1% profit
        )

        # Should pass with 1% threshold
        opp = state.check_underpriced(min_profit=1.0)
        assert opp is not None

        # Should fail with 2% threshold
        opp = state.check_underpriced(min_profit=2.0)
        assert opp is None


# =============================================================================
# NegRiskEventState Tests (Multi-outcome Events)
# =============================================================================


class TestNegRiskEventState:
    """Tests for NegRiskEventState class"""

    def test_underpriced_detection(self):
        """Detect underpriced when sum of YES prices < $1"""
        state = NegRiskEventState(
            event_id="event_1",
            title="Who will win?",
            slug="who-will-win",
            total_liquidity=100000.0,
        )

        # 5 candidates with prices summing to $0.88
        state.markets = {
            "m1": ("yes_1", "Candidate A"),
            "m2": ("yes_2", "Candidate B"),
            "m3": ("yes_3", "Candidate C"),
            "m4": ("yes_4", "Candidate D"),
            "m5": ("yes_5", "Candidate E"),
        }
        state.yes_prices = {
            "yes_1": 0.20,
            "yes_2": 0.18,
            "yes_3": 0.17,
            "yes_4": 0.16,
            "yes_5": 0.17,
        }

        opp = state.check_underpriced(min_profit=1.0)

        assert opp is not None
        assert opp["type"] == "NEGRISK_UNDERPRICED"
        assert opp["total_cost"] == pytest.approx(0.88)
        assert opp["profit"] == pytest.approx(0.12)
        assert opp["profit_percent"] == pytest.approx(13.64, rel=0.01)
        assert opp["num_outcomes"] == 5

    def test_no_underpriced_when_sum_exceeds_one(self):
        """No opportunity when sum of YES prices >= $1"""
        state = NegRiskEventState(
            event_id="event_1",
            title="Who will win?",
            slug="who-will-win",
            total_liquidity=100000.0,
        )

        state.markets = {
            "m1": ("yes_1", "Team A"),
            "m2": ("yes_2", "Team B"),
            "m3": ("yes_3", "Team C"),
            "m4": ("yes_4", "Team D"),
        }
        state.yes_prices = {
            "yes_1": 0.28,
            "yes_2": 0.27,
            "yes_3": 0.26,
            "yes_4": 0.24,  # Total = 1.05
        }

        opp = state.check_underpriced(min_profit=1.0)
        assert opp is None

    def test_overpriced_detection(self):
        """Detect overpriced when sum of YES bids > $1"""
        state = NegRiskEventState(
            event_id="event_1",
            title="Who will win?",
            slug="who-will-win",
            total_liquidity=100000.0,
        )

        state.markets = {
            "m1": ("yes_1", "Candidate A"),
            "m2": ("yes_2", "Candidate B"),
            "m3": ("yes_3", "Candidate C"),
        }
        state.yes_bids = {
            "yes_1": 0.40,
            "yes_2": 0.35,
            "yes_3": 0.30,  # Total = 1.05
        }

        opp = state.check_overpriced(min_profit=1.0)

        assert opp is not None
        assert opp["type"] == "NEGRISK_OVERPRICED"
        assert opp["total_value"] == pytest.approx(1.05)
        assert opp["profit"] == pytest.approx(0.05)
        assert opp["profit_percent"] == pytest.approx(5.0)

    def test_requires_minimum_outcomes(self):
        """NegRisk needs at least 3 outcomes"""
        state = NegRiskEventState(
            event_id="event_1",
            title="Test",
            slug="test",
            total_liquidity=100000.0,
        )

        # Only 2 outcomes
        state.markets = {
            "m1": ("yes_1", "A"),
            "m2": ("yes_2", "B"),
        }
        state.yes_prices = {
            "yes_1": 0.40,
            "yes_2": 0.40,
        }

        opp = state.check_underpriced(min_profit=1.0)
        assert opp is None

    def test_update_price(self):
        """Test price updates via token_id"""
        state = NegRiskEventState(
            event_id="event_1",
            title="Test",
            slug="test",
            total_liquidity=100000.0,
        )

        state.markets = {
            "m1": ("yes_1", "A"),
        }

        # Update price
        state.update_price("yes_1", bid=0.18, ask=0.20)
        assert state.yes_prices["yes_1"] == 0.20
        assert state.yes_bids["yes_1"] == 0.18


# =============================================================================
# RealtimeArbitrageDetector Tests
# =============================================================================


class TestRealtimeArbitrageDetector:
    """Tests for RealtimeArbitrageDetector class"""

    def test_register_binary_market(self):
        """Test registering a binary market"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.45,
            no_ask=0.48,
        )

        assert "m1" in detector.binary_markets
        assert "yes_1" in detector.token_to_market
        assert "no_1" in detector.token_to_market
        assert detector.token_to_market["yes_1"] == "m1"

    def test_register_ignores_low_liquidity(self):
        """Markets below min_liquidity are ignored"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=500.0,  # Below threshold
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
        )

        assert "m1" not in detector.binary_markets

    def test_process_message_updates_prices(self):
        """WebSocket messages update market prices"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
        )

        # Process a price update message
        message = {"asset_id": "yes_1", "best_bid": "0.43", "best_ask": "0.45"}
        detector.process_message(message)

        state = detector.binary_markets["m1"]
        assert state.yes_ask == 0.45
        assert state.yes_bid == 0.43

    def test_process_message_detects_opportunity(self):
        """Processing messages can detect arbitrage"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        # Register market with one price
        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.45,
        )

        # Process NO price update that creates opportunity
        message = {"asset_id": "no_1", "best_ask": "0.48"}
        opportunities = detector.process_message(message)

        assert len(opportunities) >= 1
        assert any(o["type"] == "BINARY_UNDERPRICED" for o in opportunities)

    def test_process_message_list(self):
        """Can process a list of messages"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
        )

        # Process multiple updates at once
        messages = [
            {"asset_id": "yes_1", "best_ask": "0.45"},
            {"asset_id": "no_1", "best_ask": "0.48"},
        ]
        opportunities = detector.process_message(messages)

        assert len(opportunities) >= 1

    def test_deduplication(self):
        """Same opportunity is not reported twice"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.45,
            no_ask=0.48,
        )

        # First message triggers opportunity
        message = {"asset_id": "yes_1", "best_ask": "0.45"}
        opps1 = detector.process_message(message)

        # Same message again should not trigger again
        opps2 = detector.process_message(message)

        assert len(opps2) == 0  # Already seen

    def test_callback_invoked(self):
        """Opportunity callback is invoked"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        callback_received = []

        def callback(opp):
            callback_received.append(opp)

        detector.on_opportunity = callback

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.45,
            no_ask=0.48,
        )

        # Trigger opportunity
        detector.process_message({"asset_id": "yes_1", "best_ask": "0.45"})

        assert len(callback_received) >= 1

    def test_get_all_token_ids(self):
        """Get all token IDs for subscription"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
        )

        detector.register_negrisk_event(
            event_id="e1",
            title="Event",
            slug="event",
            total_liquidity=100000.0,
            markets=[
                {"market_id": "m2", "yes_token_id": "yes_2", "question": "A?"},
                {"market_id": "m3", "yes_token_id": "yes_3", "question": "B?"},
                {"market_id": "m4", "yes_token_id": "yes_4", "question": "C?"},
            ],
        )

        token_ids = detector.get_all_token_ids()

        assert "yes_1" in token_ids
        assert "no_1" in token_ids
        assert "yes_2" in token_ids
        assert "yes_3" in token_ids
        assert "yes_4" in token_ids
        assert len(token_ids) == 5

    def test_get_stats(self):
        """Get detector statistics"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.45,
            no_ask=0.48,
        )

        # Process a message
        detector.process_message({"asset_id": "yes_1", "best_ask": "0.45"})

        stats = detector.get_stats()

        assert stats["binary_markets"] == 1
        assert stats["negrisk_events"] == 0
        assert stats["total_tokens"] == 2
        assert stats["messages_processed"] == 1
        assert stats["opportunities_found"] >= 1

    def test_clear_seen(self):
        """Clear seen opportunities allows re-detection"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.45,
            no_ask=0.48,
        )

        # First detection
        message = {"asset_id": "yes_1", "best_ask": "0.45"}
        opps1 = detector.process_message(message)
        assert len(opps1) >= 1

        # Second time - deduplicated
        opps2 = detector.process_message(message)
        assert len(opps2) == 0

        # Clear seen
        detector.clear_seen()

        # Now should detect again
        opps3 = detector.process_message(message)
        assert len(opps3) >= 1


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestWebSocketEdgeCases:
    """Edge case tests for WebSocket detection"""

    def test_invalid_message_format(self):
        """Invalid messages are handled gracefully"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        # Various invalid formats
        assert detector.process_message(None) == []
        assert detector.process_message("not a dict") == []
        assert detector.process_message(123) == []
        assert detector.process_message({}) == []
        assert detector.process_message({"no_asset_id": True}) == []

    def test_unregistered_token(self):
        """Messages for unregistered tokens are ignored"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        message = {"asset_id": "unknown_token", "best_ask": "0.50"}
        opps = detector.process_message(message)

        assert len(opps) == 0

    def test_price_parsing_various_formats(self):
        """Handle different price message formats"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            no_ask=0.48,
        )

        # Format 1: best_ask as string
        detector.process_message({"asset_id": "yes_1", "best_ask": "0.45"})
        assert detector.binary_markets["m1"].yes_ask == 0.45

        # Format 2: price field
        detector.process_message({"asset_id": "yes_1", "price": 0.44})
        assert detector.binary_markets["m1"].yes_ask == 0.44

        # Format 3: bids/asks arrays
        detector.process_message({
            "asset_id": "yes_1",
            "asks": [{"price": 0.43, "size": 100}],
        })
        assert detector.binary_markets["m1"].yes_ask == 0.43

    def test_simultaneous_underpriced_and_overpriced(self):
        """Market can be both underpriced and overpriced (wide spread)"""
        detector = RealtimeArbitrageDetector(min_profit_percent=1.0, min_liquidity=1000)

        # Unusual case: wide bid-ask spreads creating both opportunities
        detector.register_binary_market(
            market_id="m1",
            question="Test?",
            slug="test",
            liquidity=50000.0,
            category="crypto",
            yes_token_id="yes_1",
            no_token_id="no_1",
            yes_ask=0.40,
            no_ask=0.40,  # Underpriced: 0.80
            yes_bid=0.60,
            no_bid=0.60,  # Overpriced: 1.20
        )

        state = detector.binary_markets["m1"]
        underpriced = state.check_underpriced(1.0)
        overpriced = state.check_overpriced(1.0)

        assert underpriced is not None
        assert overpriced is not None
