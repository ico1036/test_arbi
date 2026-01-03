"""Paper Trading Engine - PoC for arbitrage strategy validation"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Callable

from .models import Position, Trade, TradingSession, PositionStatus


class PaperTradingEngine:
    """
    Simple paper trading engine for PoC.

    - Tracks virtual balance
    - Executes arbitrage opportunities instantly (optimistic)
    - Calculates P&L
    - Logs all trades

    Usage:
        engine = PaperTradingEngine(initial_balance=10000)
        engine.on_trade = lambda t: print(f"Trade: {t}")

        # Connect to detector
        detector.on_opportunity = engine.execute_opportunity

        # Get status
        engine.print_status()
    """

    def __init__(
        self,
        initial_balance: float = 10000,
        position_size: float = 100,  # Fixed size per trade
        max_position_pct: float = 0.10,  # Max 10% of balance per trade
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position_size = position_size
        self.max_position_pct = max_position_pct

        # State
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.session = TradingSession(
            start_time=datetime.now(),
            initial_balance=initial_balance,
        )

        # Callbacks
        self.on_trade: Optional[Callable[[Trade], None]] = None
        self.on_position_open: Optional[Callable[[Position], None]] = None
        self.on_position_close: Optional[Callable[[Position], None]] = None

        # Stats
        self.opportunities_seen = 0
        self.opportunities_executed = 0
        self.opportunities_skipped = 0

    def execute_opportunity(self, opportunity: Dict) -> bool:
        """
        Execute an arbitrage opportunity (paper trade).

        For PoC: Instant execution, no slippage, always succeeds.
        """
        self.opportunities_seen += 1

        # Calculate position size
        size = self._calculate_size(opportunity)
        if size <= 0:
            self.opportunities_skipped += 1
            return False

        # Calculate cost based on arbitrage type
        arb_type = opportunity.get("type", "")

        if "UNDERPRICED" in arb_type:
            # Buy YES + NO at ask prices
            total_cost = opportunity.get("total_cost", 0.97)
            cost = size * total_cost
            expected_return = size  # $1.00 per pair
        elif "OVERPRICED" in arb_type:
            # Mint at $1.00, sell at bid prices
            total_value = opportunity.get("total_value", 1.03)
            cost = size  # $1.00 to mint
            expected_return = size * total_value
        else:
            self.opportunities_skipped += 1
            return False

        # Check balance
        if cost > self.balance:
            self.opportunities_skipped += 1
            return False

        # Execute trade (deduct balance)
        self.balance -= cost

        # Create position
        profit = expected_return - cost
        profit_percent = opportunity.get("profit_percent", (profit / cost) * 100)

        position = Position(
            id=str(uuid.uuid4())[:8],
            market_id=opportunity.get("market_id", opportunity.get("event_id", "")),
            question=opportunity.get("question", opportunity.get("title", ""))[:50],
            arb_type=arb_type,
            entry_time=datetime.now(),
            entry_cost=cost,
            size=size,
            expected_profit=profit,
            profit_percent=profit_percent,
        )

        # For PoC: Instantly close position (assume settlement)
        # In real trading, position would stay open until market settles
        position.close(actual_profit=profit)
        self.balance += expected_return

        # Record
        self.positions[position.id] = position
        self.opportunities_executed += 1

        # Create trade record
        trade = Trade(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(),
            market_id=position.market_id,
            arb_type=arb_type,
            side="ARB",
            price=total_cost if "UNDERPRICED" in arb_type else 1.0,
            size=size,
            total=cost,
        )
        self.trades.append(trade)

        # Update session stats
        self.session.total_trades += 1
        if profit > 0:
            self.session.winning_trades += 1
        self.session.total_pnl += profit

        # Callbacks
        if self.on_trade:
            self.on_trade(trade)
        if self.on_position_open:
            self.on_position_open(position)
        if self.on_position_close:
            self.on_position_close(position)

        return True

    def _calculate_size(self, opportunity: Dict) -> float:
        """Calculate position size for an opportunity.

        Returns the requested position_size, capped by liquidity only.
        Balance check happens separately in execute_opportunity().
        """
        # Zero liquidity = no trade possible
        liquidity = opportunity.get("liquidity", 0)
        if liquidity <= 0:
            return 0

        size = self.position_size

        # Cap at available liquidity (5% of market liquidity)
        liquidity_cap = liquidity * 0.05
        size = min(size, liquidity_cap)

        return size

    @property
    def realized_pnl(self) -> float:
        """Total realized P&L from closed positions"""
        return sum(
            p.actual_profit or 0
            for p in self.positions.values()
            if p.status == PositionStatus.CLOSED
        )

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized P&L from open positions"""
        return sum(
            p.expected_profit
            for p in self.positions.values()
            if p.status == PositionStatus.OPEN
        )

    @property
    def total_pnl(self) -> float:
        """Total P&L"""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def return_percent(self) -> float:
        """Return percentage"""
        return (self.total_pnl / self.initial_balance) * 100

    @property
    def win_rate(self) -> float:
        """Win rate"""
        closed = [p for p in self.positions.values() if p.status == PositionStatus.CLOSED]
        if not closed:
            return 0
        winners = [p for p in closed if (p.actual_profit or 0) > 0]
        return len(winners) / len(closed)

    def get_status(self) -> Dict:
        """Get current trading status"""
        runtime = (datetime.now() - self.session.start_time).total_seconds()
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)

        open_positions = [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
        closed_positions = [p for p in self.positions.values() if p.status == PositionStatus.CLOSED]

        return {
            "runtime": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "runtime_seconds": runtime,
            "initial_balance": self.initial_balance,
            "balance": self.balance,
            "open_positions": len(open_positions),
            "closed_positions": len(closed_positions),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_pnl": self.total_pnl,
            "return_percent": self.return_percent,
            "win_rate": self.win_rate,
            "opportunities_seen": self.opportunities_seen,
            "opportunities_executed": self.opportunities_executed,
            "opportunities_skipped": self.opportunities_skipped,
        }

    def print_status(self):
        """Print formatted status"""
        s = self.get_status()

        print()
        print("=" * 64)
        print("  PAPER TRADING STATUS")
        print("=" * 64)
        print(f"  Runtime: {s['runtime']}")
        print(f"  Balance: ${s['balance']:,.2f}  (Initial: ${s['initial_balance']:,.2f})")
        print(f"  Positions: {s['open_positions']} open, {s['closed_positions']} closed")
        print("-" * 64)
        print(f"  Realized P&L:   ${s['realized_pnl']:+,.2f}")
        print(f"  Unrealized P&L: ${s['unrealized_pnl']:+,.2f}")
        print(f"  Total P&L:      ${s['total_pnl']:+,.2f} ({s['return_percent']:+.2f}%)")
        print("-" * 64)
        print(f"  Win Rate: {s['win_rate']*100:.1f}%")
        print(f"  Opportunities: {s['opportunities_executed']}/{s['opportunities_seen']} executed")
        print("=" * 64)
        print()

    def print_recent_trades(self, n: int = 5):
        """Print recent trades"""
        recent = self.trades[-n:] if self.trades else []

        if not recent:
            print("  No trades yet")
            return

        print("\n  Recent Trades:")
        for t in reversed(recent):
            time_str = t.timestamp.strftime("%H:%M:%S")
            print(f"    [{time_str}] {t.arb_type} | ${t.total:.2f}")

    def get_summary(self) -> Dict:
        """Get session summary for export"""
        self.session.end_time = datetime.now()
        self.session.final_balance = self.balance
        self.session.total_pnl = self.total_pnl

        return {
            "session": {
                "start": self.session.start_time.isoformat(),
                "end": self.session.end_time.isoformat(),
                "duration_seconds": self.session.duration_seconds,
            },
            "performance": {
                "initial_balance": self.initial_balance,
                "final_balance": self.balance,
                "total_pnl": self.total_pnl,
                "return_percent": self.return_percent,
                "win_rate": self.win_rate,
            },
            "activity": {
                "opportunities_seen": self.opportunities_seen,
                "opportunities_executed": self.opportunities_executed,
                "opportunities_skipped": self.opportunities_skipped,
            },
            "trades": [
                {
                    "id": t.id,
                    "timestamp": t.timestamp.isoformat(),
                    "market_id": t.market_id,
                    "arb_type": t.arb_type,
                    "size": t.size,
                    "total": t.total,
                }
                for t in self.trades
            ],
        }
