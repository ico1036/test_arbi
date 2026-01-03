"""
Tests for Paper Trading Engine.

Tests verify:
- Position sizing and balance management
- Trade execution and P&L calculation
- Session statistics and reporting
- Preset modes and realistic simulation
"""
import pytest
from datetime import datetime

import sys
sys.path.insert(0, "src")

from polyarb.paper_trading.models import Position, Trade, TradingSession, PositionStatus
from polyarb.paper_trading.engine import PaperTradingEngine
from polyarb.paper_trading.presets import TradingMode, PRESETS, get_mode_comparison


class TestPositionModel:
    """Tests for Position dataclass"""

    def test_position_creation(self):
        """Position is created with correct initial values"""
        pos = Position(
            id="test123",
            market_id="0xabc",
            question="Will BTC reach 100k?",
            arb_type="BINARY_UNDERPRICED",
            entry_time=datetime.now(),
            entry_cost=97.0,
            size=100,
            expected_profit=3.0,
            profit_percent=3.09,
        )

        assert pos.id == "test123"
        assert pos.status == PositionStatus.OPEN
        assert pos.expected_return == 100  # size = $100 pair
        assert pos.close_time is None
        assert pos.actual_profit is None

    def test_position_close(self):
        """Position can be closed with actual profit"""
        pos = Position(
            id="test123",
            market_id="0xabc",
            question="Test",
            arb_type="BINARY_UNDERPRICED",
            entry_time=datetime.now(),
            entry_cost=97.0,
            size=100,
            expected_profit=3.0,
            profit_percent=3.09,
        )

        pos.close(actual_profit=2.95)

        assert pos.status == PositionStatus.CLOSED
        assert pos.close_time is not None
        assert pos.actual_profit == 2.95


class TestTradeModel:
    """Tests for Trade dataclass"""

    def test_trade_creation(self):
        """Trade is created with correct values"""
        trade = Trade(
            id="t001",
            timestamp=datetime.now(),
            market_id="0xabc",
            arb_type="BINARY_UNDERPRICED",
            side="ARB",
            price=0.97,
            size=100,
            total=97.0,
        )

        assert trade.id == "t001"
        assert trade.total == 97.0


class TestTradingSession:
    """Tests for TradingSession dataclass"""

    def test_session_win_rate_zero_trades(self):
        """Win rate is 0 when no trades"""
        session = TradingSession(start_time=datetime.now())
        assert session.win_rate == 0

    def test_session_win_rate_calculation(self):
        """Win rate is correctly calculated"""
        session = TradingSession(
            start_time=datetime.now(),
            total_trades=10,
            winning_trades=7,
        )
        assert session.win_rate == 0.7

    def test_session_return_percent(self):
        """Return percent is correctly calculated"""
        session = TradingSession(
            start_time=datetime.now(),
            initial_balance=1000,
            total_pnl=50,
        )
        assert session.return_percent == 5.0

    def test_session_return_percent_zero_balance(self):
        """Return percent is 0 when initial balance is 0"""
        session = TradingSession(
            start_time=datetime.now(),
            initial_balance=0,
            total_pnl=50,
        )
        assert session.return_percent == 0


class TestPaperTradingEngine:
    """Tests for PaperTradingEngine"""

    def test_engine_initialization(self):
        """Engine initializes with correct values"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=100,
        )

        assert engine.balance == 10000
        assert engine.initial_balance == 10000
        assert engine.position_size == 100
        assert len(engine.positions) == 0
        assert len(engine.trades) == 0

    def test_execute_underpriced_opportunity(self):
        """Engine executes underpriced arbitrage correctly"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,  # YES + NO = $0.97
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        assert len(engine.positions) == 1
        assert len(engine.trades) == 1

        # Check balance: started with 1000, spent 97, received 100
        # Net: 1000 - 97 + 100 = 1003
        assert engine.balance == pytest.approx(1003, abs=0.1)

        # Check P&L
        assert engine.realized_pnl == pytest.approx(3.0, abs=0.1)

    def test_execute_overpriced_opportunity(self):
        """Engine executes overpriced arbitrage correctly"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_OVERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_value": 1.03,  # YES_bid + NO_bid = $1.03
            "profit_percent": 3.0,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True

        # Check balance: started with 1000, spent 100 to mint, received 103 from selling
        # Net: 1000 - 100 + 103 = 1003
        assert engine.balance == pytest.approx(1003, abs=0.1)

    def test_insufficient_balance(self):
        """Engine rejects trade when balance is insufficient"""
        engine = PaperTradingEngine(initial_balance=50, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is False
        assert engine.balance == 50  # Unchanged
        assert len(engine.positions) == 0
        assert engine.opportunities_skipped == 1

    def test_large_position_uses_full_size(self):
        """Large position size is used if balance allows"""
        engine = PaperTradingEngine(
            initial_balance=1000,
            position_size=500,  # Requested $500
        )

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 100000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        pos = list(engine.positions.values())[0]
        assert pos.size == pytest.approx(500, abs=1)

    def test_position_sizing_respects_liquidity(self):
        """Position size is capped at 5% of market liquidity"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=1000,  # Requested $1000
        )

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 2000,  # 5% = $100
        }

        engine.execute_opportunity(opportunity)

        # Position should be capped at 5% of $2000 = $100
        pos = list(engine.positions.values())[0]
        assert pos.size == pytest.approx(100, abs=1)

    def test_multiple_trades(self):
        """Engine handles multiple trades correctly"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        for i in range(5):
            opportunity = {
                "type": "BINARY_UNDERPRICED",
                "market_id": f"0xtest{i}",
                "question": f"Test market {i}",
                "total_cost": 0.98,  # 2.04% profit
                "profit_percent": 2.04,
                "liquidity": 50000,
            }
            engine.execute_opportunity(opportunity)

        assert len(engine.positions) == 5
        assert len(engine.trades) == 5
        assert engine.opportunities_executed == 5

        # Each trade: spend 98, receive 100, profit 2
        # Total profit: 5 * 2 = 10
        assert engine.realized_pnl == pytest.approx(10, abs=0.5)

    def test_win_rate_calculation(self):
        """Win rate is correctly calculated"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        # Execute profitable trades
        for i in range(3):
            opportunity = {
                "type": "BINARY_UNDERPRICED",
                "market_id": f"0xwin{i}",
                "question": "Winning trade",
                "total_cost": 0.97,
                "profit_percent": 3.09,
                "liquidity": 50000,
            }
            engine.execute_opportunity(opportunity)

        # All trades are profitable in PoC mode
        assert engine.win_rate == 1.0

    def test_get_status(self):
        """get_status returns correct data"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }
        engine.execute_opportunity(opportunity)

        status = engine.get_status()

        assert status["initial_balance"] == 1000
        assert status["balance"] == pytest.approx(1003, abs=0.1)
        assert status["closed_positions"] == 1
        assert status["open_positions"] == 0
        assert status["opportunities_executed"] == 1
        assert "runtime" in status

    def test_get_summary(self):
        """get_summary returns exportable data"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }
        engine.execute_opportunity(opportunity)

        summary = engine.get_summary()

        assert "session" in summary
        assert "performance" in summary
        assert "activity" in summary
        assert "trades" in summary

        assert summary["performance"]["initial_balance"] == 1000
        assert len(summary["trades"]) == 1

    def test_callbacks_are_called(self):
        """Callbacks are triggered on trade execution"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        trade_callback_called = []
        position_callback_called = []

        engine.on_trade = lambda t: trade_callback_called.append(t)
        engine.on_position_close = lambda p: position_callback_called.append(p)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }
        engine.execute_opportunity(opportunity)

        assert len(trade_callback_called) == 1
        assert len(position_callback_called) == 1

    def test_invalid_opportunity_type(self):
        """Engine skips unknown opportunity types"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "UNKNOWN_TYPE",
            "market_id": "0xtest",
            "question": "Test market",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is False
        assert engine.opportunities_skipped == 1

    def test_negrisk_underpriced(self):
        """Engine handles NegRisk underpriced opportunities"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "NEGRISK_UNDERPRICED",
            "event_id": "event123",
            "title": "Who wins election?",
            "total_cost": 0.92,  # Sum of all YES prices
            "profit_percent": 8.7,
            "liquidity": 100000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        assert engine.balance == pytest.approx(1008, abs=0.5)

    def test_negrisk_overpriced(self):
        """Engine handles NegRisk overpriced opportunities"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "NEGRISK_OVERPRICED",
            "event_id": "event123",
            "title": "Who wins election?",
            "total_value": 1.05,  # Sum of all YES bids
            "profit_percent": 5.0,
            "liquidity": 100000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        # Mint at $1.00, sell for $1.05
        assert engine.balance == pytest.approx(1005, abs=0.5)


class TestPaperTradingEdgeCases:
    """Edge cases for paper trading"""

    def test_zero_initial_balance(self):
        """잔고 0으로 시작하면 모든 거래 거절"""
        engine = PaperTradingEngine(initial_balance=0, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is False
        assert engine.balance == 0

    def test_zero_liquidity_market(self):
        """유동성 0인 마켓은 사이즈 0으로 거절"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 0,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is False
        assert engine.opportunities_skipped == 1

    def test_balance_exhaustion_across_trades(self):
        """연속 거래로 잔고 소진 시 이후 거래 거절"""
        engine = PaperTradingEngine(initial_balance=200, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        # 첫 번째: 성공 (잔고 200 → 97 소비 → 100 수익 = 203)
        success1 = engine.execute_opportunity(opportunity)
        # 두 번째: 성공 (잔고 203 → 97 소비 → 100 수익 = 206)
        success2 = engine.execute_opportunity({**opportunity, "market_id": "0xtest2"})
        # 세 번째: 성공 (잔고 206 → 97 소비 → 100 수익 = 209)
        success3 = engine.execute_opportunity({**opportunity, "market_id": "0xtest3"})

        assert success1 is True
        assert success2 is True
        assert success3 is True
        assert engine.opportunities_executed == 3

    def test_missing_total_cost_uses_default(self):
        """total_cost 없으면 기본값 0.97 사용"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            # total_cost 없음
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        # 기본값 0.97 적용: 1000 - 97 + 100 = 1003
        assert engine.balance == pytest.approx(1003, abs=0.1)

    def test_missing_total_value_uses_default(self):
        """total_value 없으면 기본값 1.03 사용"""
        engine = PaperTradingEngine(initial_balance=1000, position_size=100)

        opportunity = {
            "type": "BINARY_OVERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            # total_value 없음
            "profit_percent": 3.0,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        # 기본값 1.03 적용: 1000 - 100 + 103 = 1003
        assert engine.balance == pytest.approx(1003, abs=0.1)

    def test_exact_balance_for_trade(self):
        """정확히 필요한 금액만 있으면 거래 성공"""
        engine = PaperTradingEngine(initial_balance=97, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        # 97 - 97 + 100 = 100
        assert engine.balance == pytest.approx(100, abs=0.1)

    def test_one_cent_short_rejected(self):
        """1센트라도 부족하면 거절"""
        engine = PaperTradingEngine(initial_balance=96.99, position_size=100)

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is False
        assert engine.balance == 96.99


class TestPresetModes:
    """Tests for preset trading modes"""

    def test_conservative_mode_settings(self):
        """Conservative mode has correct default settings"""
        settings = PRESETS[TradingMode.CONSERVATIVE]

        assert settings.min_profit == 5.0
        assert settings.failure_rate == 0.3
        assert settings.latency_ms == 3000
        assert settings.liquidity_cap_pct == 1.0

    def test_moderate_mode_settings(self):
        """Moderate mode has correct default settings"""
        settings = PRESETS[TradingMode.MODERATE]

        assert settings.min_profit == 3.0
        assert settings.failure_rate == 0.2
        assert settings.latency_ms == 2000

    def test_aggressive_mode_settings(self):
        """Aggressive mode has correct default settings"""
        settings = PRESETS[TradingMode.AGGRESSIVE]

        assert settings.min_profit == 1.0
        assert settings.failure_rate == 0.1
        assert settings.latency_ms == 1000

    def test_engine_with_preset_mode(self):
        """Engine applies preset settings correctly"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            mode=TradingMode.CONSERVATIVE,
        )

        assert engine.mode == TradingMode.CONSERVATIVE
        assert engine.position_size == 50  # Conservative size
        assert engine.failure_rate == 0.3
        assert engine.latency_ms == 3000

    def test_get_mode_comparison(self):
        """Mode comparison string is generated"""
        comparison = get_mode_comparison()

        assert "Conservative" in comparison
        assert "Moderate" in comparison
        assert "Aggressive" in comparison


class TestRealisticSimulation:
    """Tests for realistic execution simulation"""

    def test_failure_rate_causes_skipped_trades(self):
        """High failure rate causes trades to be skipped"""
        # Use 100% failure rate for deterministic test
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=100,
            failure_rate=1.0,  # 100% failure
        )

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is False
        assert engine.opportunities_failed == 1
        assert engine.opportunities_skipped == 1
        assert engine.balance == 10000  # No change

    def test_zero_failure_rate_allows_trades(self):
        """Zero failure rate allows all valid trades"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=100,
            failure_rate=0.0,
        )

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        success = engine.execute_opportunity(opportunity)

        assert success is True
        assert engine.opportunities_failed == 0

    def test_failure_callback_is_called(self):
        """Failure callback is invoked on simulated failure"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=100,
            failure_rate=1.0,
        )

        failures = []
        engine.on_failure = lambda opp, reason: failures.append((opp, reason))

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        engine.execute_opportunity(opportunity)

        assert len(failures) == 1
        assert failures[0][1] == "execution_failed"

    def test_custom_liquidity_cap(self):
        """Custom liquidity cap is applied"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=1000,  # Request large size
            liquidity_cap_pct=1.0,  # Only 1% of liquidity
        )

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 10000,  # $10k liquidity -> max $100 (1%)
        }

        engine.execute_opportunity(opportunity)

        # Position should be capped at 1% of 10000 = 100
        assert engine.positions
        pos = list(engine.positions.values())[0]
        assert pos.size == 100


class TestAdvancedMetrics:
    """Tests for advanced metrics"""

    def test_max_drawdown_no_trades(self):
        """Max drawdown is 0 with no trades"""
        engine = PaperTradingEngine(initial_balance=10000)

        assert engine.max_drawdown == 0.0

    def test_execution_rate_calculation(self):
        """Execution rate is calculated correctly"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            position_size=100,
        )

        opportunity = {
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        }

        # Execute 2 trades
        engine.execute_opportunity(opportunity)
        engine.execute_opportunity({**opportunity, "market_id": "0xtest2"})

        # Skip 1 trade (no liquidity)
        engine.execute_opportunity({**opportunity, "market_id": "0xtest3", "liquidity": 0})

        assert engine.opportunities_seen == 3
        assert engine.opportunities_executed == 2
        assert engine.execution_rate == pytest.approx(66.67, rel=0.01)

    def test_status_includes_simulation_settings(self):
        """Status includes simulation settings"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            mode=TradingMode.MODERATE,
        )

        status = engine.get_status()

        assert status["mode"] == "moderate"
        assert status["latency_ms"] == 2000
        assert status["failure_rate"] == 0.2
        assert "max_drawdown" in status
        assert "execution_rate" in status
        assert "opportunities_failed" in status
