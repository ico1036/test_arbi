"""
Tests for Summary Chart Generation.

TDD: Tests written first.
"""
import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, "src")

from polyarb.paper_trading.engine import PaperTradingEngine
from polyarb.paper_trading.presets import TradingMode
from polyarb.paper_trading.summary_chart import SummaryChart


class TestSummaryChartGeneration:
    """Tests for PNG summary chart generation"""

    def test_generate_chart_creates_file(self):
        """generate() creates a PNG file"""
        engine = PaperTradingEngine(initial_balance=10000, position_size=100)

        # Execute some trades
        for i in range(5):
            engine.execute_opportunity({
                "type": "BINARY_UNDERPRICED",
                "market_id": f"0xtest{i}",
                "question": f"Test {i}",
                "total_cost": 0.97,
                "profit_percent": 3.09,
                "liquidity": 50000,
            })

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "summary.png"

            chart = SummaryChart(engine)
            result = chart.save(str(filepath))

            assert filepath.exists()
            assert result == str(filepath)

    def test_generate_chart_with_no_trades(self):
        """Chart generation works with no trades"""
        engine = PaperTradingEngine(initial_balance=10000)

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty.png"

            chart = SummaryChart(engine)
            result = chart.save(str(filepath))

            assert filepath.exists()

    def test_chart_shows_key_metrics(self):
        """Chart includes key metrics in title/labels"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            mode=TradingMode.MODERATE,
        )

        chart = SummaryChart(engine)

        # Check that chart data includes key metrics
        assert chart.metrics["mode"] == "moderate"
        assert chart.metrics["initial_balance"] == 10000

    def test_chart_with_preset_mode(self):
        """Chart correctly shows preset mode info"""
        engine = PaperTradingEngine(
            initial_balance=10000,
            mode=TradingMode.CONSERVATIVE,
        )

        engine.execute_opportunity({
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.95,
            "profit_percent": 5.26,
            "liquidity": 50000,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "conservative.png"

            chart = SummaryChart(engine)
            chart.save(str(filepath))

            assert filepath.exists()
            # File should be non-empty PNG
            assert filepath.stat().st_size > 1000


class TestSummaryChartMetrics:
    """Tests for metrics extraction"""

    def test_metrics_include_pnl(self):
        """Metrics include P&L data"""
        engine = PaperTradingEngine(initial_balance=10000, position_size=100)

        engine.execute_opportunity({
            "type": "BINARY_UNDERPRICED",
            "market_id": "0xtest",
            "question": "Test",
            "total_cost": 0.97,
            "profit_percent": 3.09,
            "liquidity": 50000,
        })

        chart = SummaryChart(engine)

        assert "total_pnl" in chart.metrics
        assert "return_percent" in chart.metrics
        assert chart.metrics["total_pnl"] > 0

    def test_metrics_include_trade_stats(self):
        """Metrics include trade statistics"""
        engine = PaperTradingEngine(initial_balance=10000, position_size=100)

        for i in range(3):
            engine.execute_opportunity({
                "type": "BINARY_UNDERPRICED",
                "market_id": f"0xtest{i}",
                "question": f"Test {i}",
                "total_cost": 0.97,
                "profit_percent": 3.09,
                "liquidity": 50000,
            })

        chart = SummaryChart(engine)

        assert chart.metrics["opportunities_executed"] == 3
        assert "win_rate" in chart.metrics
