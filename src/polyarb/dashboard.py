"""
Paper Trading Dashboard - Real-time visualization with NiceGUI

Usage:
    uv run python -m polyarb.dashboard
    uv run python -m polyarb.dashboard --mode moderate
"""
import asyncio
from datetime import datetime
from typing import Optional

from nicegui import ui, app

from .paper_trading import PaperTradingEngine, TradingMode, PRESETS, get_mode_comparison


class Dashboard:
    """NiceGUI-based paper trading dashboard"""

    def __init__(self):
        self.engine: Optional[PaperTradingEngine] = None
        self.running = False
        self.pnl_history: list[tuple[datetime, float]] = []
        self.trade_log: list[dict] = []

        # UI elements
        self.balance_label = None
        self.pnl_label = None
        self.trades_label = None
        self.win_rate_label = None
        self.chart = None
        self.log_container = None
        self.status_indicator = None

    def create_engine(self, mode: TradingMode, balance: float):
        """Create paper trading engine with preset mode"""
        self.engine = PaperTradingEngine(
            initial_balance=balance,
            mode=mode,
        )
        self.engine.on_trade = self._on_trade
        self.engine.on_failure = self._on_failure
        self.pnl_history = [(datetime.now(), 0.0)]
        self.trade_log = []

    def _on_trade(self, trade):
        """Handle trade execution"""
        self.trade_log.append({
            "time": trade.timestamp.strftime("%H:%M:%S"),
            "type": trade.arb_type,
            "size": f"${trade.size:.0f}",
            "status": "executed",
        })
        self._update_chart()

    def _on_failure(self, opp, reason):
        """Handle trade failure"""
        self.trade_log.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": opp.get("type", "UNKNOWN"),
            "size": "-",
            "status": "failed",
        })

    def _update_chart(self):
        """Update P&L chart"""
        if self.engine:
            self.pnl_history.append((datetime.now(), self.engine.total_pnl))

    def _update_ui(self):
        """Update all UI elements"""
        if not self.engine:
            return

        status = self.engine.get_status()

        if self.balance_label:
            self.balance_label.text = f"${status['balance']:,.2f}"
        if self.pnl_label:
            pnl = status['total_pnl']
            color = "text-green-500" if pnl >= 0 else "text-red-500"
            self.pnl_label.text = f"${pnl:+,.2f}"
            self.pnl_label.classes(remove="text-green-500 text-red-500", add=color)
        if self.trades_label:
            self.trades_label.text = f"{status['opportunities_executed']}"
        if self.win_rate_label:
            self.win_rate_label.text = f"{status['win_rate']*100:.0f}%"

    def build_ui(self):
        """Build the dashboard UI"""
        ui.dark_mode(True)

        with ui.header().classes("bg-slate-800 justify-between"):
            ui.label("Polymarket Paper Trading").classes("text-xl font-bold")
            self.status_indicator = ui.label("STOPPED").classes(
                "px-3 py-1 rounded bg-red-600 text-white text-sm"
            )

        with ui.row().classes("w-full gap-4 p-4"):
            # Left panel - Controls
            with ui.card().classes("w-64"):
                ui.label("Settings").classes("text-lg font-bold mb-2")

                self.mode_select = ui.select(
                    label="Mode",
                    options={
                        "conservative": "Conservative (Safe)",
                        "moderate": "Moderate (Balanced)",
                        "aggressive": "Aggressive (High Risk)",
                    },
                    value="moderate",
                ).classes("w-full")

                self.balance_input = ui.number(
                    label="Initial Balance ($)",
                    value=10000,
                    min=100,
                    max=1000000,
                ).classes("w-full")

                ui.separator()

                with ui.row().classes("gap-2 w-full"):
                    self.start_btn = ui.button(
                        "Start",
                        on_click=self._start_trading,
                    ).classes("flex-1 bg-green-600")
                    self.stop_btn = ui.button(
                        "Stop",
                        on_click=self._stop_trading,
                    ).classes("flex-1 bg-red-600").props("disable")

                # Mode description
                ui.separator()
                self.mode_desc = ui.label().classes("text-xs text-gray-400")
                self._update_mode_description()
                self.mode_select.on_value_change(lambda _: self._update_mode_description())

            # Center panel - Stats
            with ui.card().classes("flex-1"):
                ui.label("Performance").classes("text-lg font-bold mb-4")

                with ui.row().classes("gap-8 justify-center"):
                    with ui.column().classes("items-center"):
                        ui.label("Balance").classes("text-gray-400 text-sm")
                        self.balance_label = ui.label("$10,000.00").classes(
                            "text-2xl font-bold"
                        )

                    with ui.column().classes("items-center"):
                        ui.label("P&L").classes("text-gray-400 text-sm")
                        self.pnl_label = ui.label("$0.00").classes(
                            "text-2xl font-bold text-green-500"
                        )

                    with ui.column().classes("items-center"):
                        ui.label("Trades").classes("text-gray-400 text-sm")
                        self.trades_label = ui.label("0").classes("text-2xl font-bold")

                    with ui.column().classes("items-center"):
                        ui.label("Win Rate").classes("text-gray-400 text-sm")
                        self.win_rate_label = ui.label("0%").classes("text-2xl font-bold")

                ui.separator()

                # Additional metrics
                with ui.row().classes("gap-4 justify-center text-sm"):
                    self.drawdown_label = ui.label("Max DD: 0%").classes("text-gray-400")
                    self.exec_rate_label = ui.label("Exec Rate: 0%").classes("text-gray-400")
                    self.failed_label = ui.label("Failed: 0").classes("text-gray-400")

            # Right panel - Trade Log
            with ui.card().classes("w-80"):
                ui.label("Trade Log").classes("text-lg font-bold mb-2")
                self.log_container = ui.column().classes("gap-1 max-h-64 overflow-auto")

        # Bottom - Chart placeholder
        with ui.card().classes("w-full mx-4 mb-4"):
            ui.label("P&L History").classes("text-lg font-bold mb-2")
            with ui.element("div").classes("h-32 bg-slate-700 rounded flex items-center justify-center"):
                ui.label("Chart updates during trading session").classes("text-gray-400")

    def _update_mode_description(self):
        """Update mode description text"""
        if self.mode_select and self.mode_desc:
            mode = TradingMode(self.mode_select.value)
            settings = PRESETS[mode]
            self.mode_desc.text = (
                f"Min Profit: {settings.min_profit}% | "
                f"Size: ${settings.position_size} | "
                f"Failure: {settings.failure_rate*100:.0f}%"
            )

    async def _start_trading(self):
        """Start paper trading session"""
        mode = TradingMode(self.mode_select.value)
        balance = self.balance_input.value

        self.create_engine(mode, balance)
        self.running = True

        self.start_btn.props("disable")
        self.stop_btn.props(remove="disable")
        self.status_indicator.text = "RUNNING"
        self.status_indicator.classes(remove="bg-red-600", add="bg-green-600")

        # Start update loop
        asyncio.create_task(self._trading_loop())

    async def _trading_loop(self):
        """Main trading loop - simulates opportunities"""
        import random

        while self.running and self.engine:
            # Simulate opportunity arrival (random)
            await asyncio.sleep(random.uniform(1, 5))

            if not self.running:
                break

            # Generate fake opportunity for demo
            profit_pct = random.uniform(1, 8)
            opp = {
                "type": random.choice(["BINARY_UNDERPRICED", "BINARY_OVERPRICED"]),
                "market_id": f"0x{random.randint(1000, 9999)}",
                "question": f"Demo Market {random.randint(1, 100)}",
                "total_cost": 1 - (profit_pct / 100),
                "total_value": 1 + (profit_pct / 100),
                "profit_percent": profit_pct,
                "liquidity": random.randint(5000, 100000),
            }

            self.engine.execute_opportunity(opp)
            self._update_ui()
            self._update_log()
            self._update_metrics()

    def _update_log(self):
        """Update trade log UI"""
        if not self.log_container:
            return

        self.log_container.clear()
        with self.log_container:
            for entry in reversed(self.trade_log[-10:]):
                color = "text-green-400" if entry["status"] == "executed" else "text-red-400"
                ui.label(
                    f"[{entry['time']}] {entry['type'][:15]} {entry['size']} - {entry['status']}"
                ).classes(f"text-xs font-mono {color}")

    def _update_metrics(self):
        """Update additional metrics"""
        if not self.engine:
            return

        status = self.engine.get_status()
        if self.drawdown_label:
            self.drawdown_label.text = f"Max DD: {status['max_drawdown']:.1f}%"
        if self.exec_rate_label:
            self.exec_rate_label.text = f"Exec Rate: {status['execution_rate']:.0f}%"
        if self.failed_label:
            self.failed_label.text = f"Failed: {status['opportunities_failed']}"

    def _stop_trading(self):
        """Stop paper trading session"""
        self.running = False

        self.start_btn.props(remove="disable")
        self.stop_btn.props("disable")
        self.status_indicator.text = "STOPPED"
        self.status_indicator.classes(remove="bg-green-600", add="bg-red-600")

        if self.engine:
            self.engine.print_status()


def run_dashboard(mode: str = "moderate", port: int = 8080):
    """Run the dashboard"""
    dashboard = Dashboard()
    dashboard.build_ui()

    print(f"\n  Dashboard starting at http://localhost:{port}")
    print("  Press Ctrl+C to stop\n")

    ui.run(
        port=port,
        title="Polymarket Paper Trading",
        reload=False,
        show=False,  # Don't auto-open browser
    )


def main():
    """Entry point for dashboard"""
    import argparse

    parser = argparse.ArgumentParser(description="Paper Trading Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port to run on")
    args = parser.parse_args()

    run_dashboard(port=args.port)


if __name__ == "__main__":
    main()
