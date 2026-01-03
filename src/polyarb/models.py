"""
Data models for Polymarket arbitrage detection
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum


class MarketType(Enum):
    """Market type classification"""
    BINARY = "binary"  # 2 outcomes (YES/NO)
    NEGRISK = "negrisk"  # Multiple outcomes (sum to 1)
    UNKNOWN = "unknown"


class ArbitrageType(Enum):
    """Type of arbitrage opportunity"""
    BINARY_UNDERPRICED = "binary_underpriced"  # YES + NO < $1
    NEGRISK_UNDERPRICED = "negrisk_underpriced"  # Sum of all YES < $1
    BINARY_OVERPRICED = "binary_overpriced"  # YES + NO > $1 (sell opportunity)
    NEGRISK_OVERPRICED = "negrisk_overpriced"  # Sum of all YES > $1


@dataclass
class Token:
    """Represents a market outcome token"""
    token_id: str
    outcome: str  # "YES", "NO", or specific outcome name
    price: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None

    # Order book depth
    bid_depth: Dict[float, float] = field(default_factory=dict)  # price -> size
    ask_depth: Dict[float, float] = field(default_factory=dict)  # price -> size


@dataclass
class Market:
    """Represents a Polymarket market"""
    market_id: str
    condition_id: str
    question: str
    slug: str
    tokens: List[Token]
    liquidity: float
    volume: float = 0
    category: str = ""
    market_type: MarketType = MarketType.UNKNOWN
    active: bool = True
    closed: bool = False

    # Computed
    neg_risk: bool = False  # True if NegRisk market

    @property
    def url(self) -> str:
        return f"https://polymarket.com/event/{self.slug}" if self.slug else ""

    @property
    def is_binary(self) -> bool:
        return len(self.tokens) == 2

    @property
    def is_multi_outcome(self) -> bool:
        return len(self.tokens) > 2


@dataclass
class OrderBookLevel:
    """Single level in order book"""
    price: float
    size: float

    @property
    def value(self) -> float:
        return self.price * self.size


@dataclass
class OrderBook:
    """Order book for a token"""
    token_id: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    def get_executable_price(self, side: str, size: float) -> Optional[float]:
        """
        Calculate average execution price for a given size.
        Returns None if insufficient liquidity.
        """
        levels = self.asks if side == "buy" else self.bids
        remaining = size
        total_cost = 0.0

        for level in levels:
            if remaining <= 0:
                break
            fill_size = min(remaining, level.size)
            total_cost += fill_size * level.price
            remaining -= fill_size

        if remaining > 0:
            return None  # Insufficient liquidity

        return total_cost / size

    def get_slippage(self, side: str, size: float) -> Optional[float]:
        """Calculate slippage % for a given size"""
        ref_price = self.best_ask if side == "buy" else self.best_bid
        exec_price = self.get_executable_price(side, size)

        if ref_price and exec_price:
            return abs(exec_price - ref_price) / ref_price * 100
        return None


@dataclass
class ArbitrageOpportunity:
    """Represents an arbitrage opportunity"""
    # Market info
    market_id: str
    condition_id: str
    question: str
    url: str
    category: str

    # Type
    arb_type: ArbitrageType
    market_type: MarketType

    # Pricing
    total_cost: float  # Total cost to acquire all outcomes
    profit: float  # Guaranteed profit ($1 - total_cost)
    profit_percent: float

    # Token details
    tokens: List[Token]

    # Market stats
    liquidity: float

    # Execution analysis
    max_executable_size: float = 0  # Max size before slippage exceeds threshold
    estimated_slippage: float = 0  # % slippage at max_executable_size

    # Timing
    timestamp: datetime = field(default_factory=datetime.now)

    # Unique key for deduplication
    @property
    def key(self) -> str:
        return f"{self.market_id}_{self.profit_percent:.2f}"

    def expected_profit(self, investment: float) -> float:
        """Calculate expected profit for a given investment"""
        return investment * (self.profit_percent / 100)

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/export"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "market_id": self.market_id,
            "question": self.question[:100],
            "arb_type": self.arb_type.value,
            "market_type": self.market_type.value,
            "total_cost": self.total_cost,
            "profit": self.profit,
            "profit_percent": self.profit_percent,
            "liquidity": self.liquidity,
            "category": self.category,
            "max_executable_size": self.max_executable_size,
            "url": self.url,
        }


@dataclass
class ScanResult:
    """Result of a market scan"""
    opportunities: List[ArbitrageOpportunity] = field(default_factory=list)
    markets_scanned: int = 0
    binary_markets: int = 0
    negrisk_markets: int = 0
    scan_duration: float = 0  # seconds
    timestamp: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)

    @property
    def total_potential_profit(self) -> float:
        return sum(o.profit for o in self.opportunities)

    @property
    def best_opportunity(self) -> Optional[ArbitrageOpportunity]:
        if not self.opportunities:
            return None
        return max(self.opportunities, key=lambda x: x.profit_percent)
