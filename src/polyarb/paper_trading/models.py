"""Data models for paper trading"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Trade:
    """Individual trade record"""
    id: str
    timestamp: datetime
    market_id: str
    arb_type: str  # BINARY_UNDERPRICED, BINARY_OVERPRICED, NEGRISK_*
    side: str  # BUY or SELL
    price: float
    size: float
    total: float


@dataclass
class Position:
    """Arbitrage position (YES + NO pair)"""
    id: str
    market_id: str
    question: str
    arb_type: str
    entry_time: datetime
    entry_cost: float  # Total cost to enter
    size: float  # Number of pairs
    expected_profit: float  # Profit if settled at $1.00
    profit_percent: float
    status: PositionStatus = PositionStatus.OPEN
    close_time: Optional[datetime] = None
    actual_profit: Optional[float] = None

    @property
    def expected_return(self) -> float:
        """Expected return when market settles"""
        return self.size  # Each pair returns $1.00

    def close(self, actual_profit: float):
        """Close the position"""
        self.status = PositionStatus.CLOSED
        self.close_time = datetime.now()
        self.actual_profit = actual_profit


@dataclass
class TradingSession:
    """Session summary"""
    start_time: datetime
    end_time: Optional[datetime] = None
    initial_balance: float = 0
    final_balance: float = 0
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0

    @property
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0
        return self.winning_trades / self.total_trades

    @property
    def return_percent(self) -> float:
        if self.initial_balance == 0:
            return 0
        return (self.total_pnl / self.initial_balance) * 100
