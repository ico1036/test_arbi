"""
Base strategy interface
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Market, ArbitrageOpportunity
from ..api.clob import CLOBClient


class Strategy(ABC):
    """Base class for arbitrage strategies"""

    def __init__(self, clob_client: CLOBClient):
        self.clob = clob_client

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name"""
        pass

    @abstractmethod
    async def analyze(self, market: Market) -> Optional[ArbitrageOpportunity]:
        """
        Analyze a market for arbitrage opportunity.
        Returns ArbitrageOpportunity if found, None otherwise.
        """
        pass

    @abstractmethod
    async def analyze_batch(
        self, markets: List[Market]
    ) -> List[ArbitrageOpportunity]:
        """
        Analyze multiple markets concurrently.
        Returns list of opportunities found.
        """
        pass

    def meets_thresholds(
        self,
        profit_percent: float,
        liquidity: float,
        min_profit: float,
        min_liquidity: float,
    ) -> bool:
        """Check if opportunity meets minimum thresholds"""
        return profit_percent >= min_profit and liquidity >= min_liquidity
