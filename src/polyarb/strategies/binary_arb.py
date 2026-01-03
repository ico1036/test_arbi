"""
Binary Arbitrage Strategy
Detects when YES + NO < $1.00 in binary markets
"""
import asyncio
from typing import List, Optional
from datetime import datetime

from .base import Strategy
from ..models import Market, ArbitrageOpportunity, ArbitrageType, MarketType
from ..api.clob import CLOBClient
from ..config import config


class BinaryArbitrageStrategy(Strategy):
    """
    Classic binary market arbitrage.

    When YES ask + NO ask < $1.00, buying both guarantees profit.
    Settlement always pays exactly $1.00 for one outcome.

    Example:
        YES ask: $0.48
        NO ask:  $0.46
        Total:   $0.94
        Profit:  $0.06 (6.38%)
    """

    def __init__(
        self,
        clob_client: CLOBClient,
        min_profit_percent: float = None,
        min_liquidity: float = None,
    ):
        super().__init__(clob_client)
        self.min_profit = min_profit_percent or config.arbitrage.min_profit_percent
        self.min_liquidity = min_liquidity or config.arbitrage.min_liquidity

    @property
    def name(self) -> str:
        return "binary_arbitrage"

    async def analyze(self, market: Market) -> Optional[ArbitrageOpportunity]:
        """Analyze a single binary market"""
        # Must be binary market with exactly 2 tokens
        if market.market_type != MarketType.BINARY or len(market.tokens) != 2:
            return None

        yes_token = market.tokens[0]
        no_token = market.tokens[1]

        # Get best ask prices concurrently
        prices = await self.clob.get_prices_batch(
            [yes_token.token_id, no_token.token_id], side="buy"
        )

        yes_price = prices.get(yes_token.token_id)
        no_price = prices.get(no_token.token_id)

        # Need both prices
        if yes_price is None or no_price is None:
            return None

        if yes_price <= 0 or no_price <= 0:
            return None

        # Calculate arbitrage
        total_cost = yes_price + no_price

        # No arbitrage if total >= $1
        if total_cost >= 1.0:
            return None

        profit = 1.0 - total_cost
        profit_percent = (profit / total_cost) * 100

        # Check thresholds
        if not self.meets_thresholds(
            profit_percent, market.liquidity, self.min_profit, self.min_liquidity
        ):
            return None

        # Update token prices
        yes_token.price = yes_price
        yes_token.best_ask = yes_price
        no_token.price = no_price
        no_token.best_ask = no_price

        return ArbitrageOpportunity(
            market_id=market.market_id,
            condition_id=market.condition_id,
            question=market.question,
            url=market.url,
            category=market.category,
            arb_type=ArbitrageType.BINARY_UNDERPRICED,
            market_type=MarketType.BINARY,
            total_cost=total_cost,
            profit=profit,
            profit_percent=profit_percent,
            tokens=[yes_token, no_token],
            liquidity=market.liquidity,
            timestamp=datetime.now(),
        )

    async def analyze_batch(
        self, markets: List[Market]
    ) -> List[ArbitrageOpportunity]:
        """Analyze multiple markets concurrently"""
        # Filter to binary markets only
        binary_markets = [m for m in markets if m.market_type == MarketType.BINARY]

        # Analyze concurrently
        tasks = [self.analyze(m) for m in binary_markets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        opportunities = []
        for result in results:
            if isinstance(result, ArbitrageOpportunity):
                opportunities.append(result)

        # Sort by profit percent descending
        opportunities.sort(key=lambda x: x.profit_percent, reverse=True)

        return opportunities

    async def analyze_with_depth(
        self, market: Market, target_size: float = 1000
    ) -> Optional[ArbitrageOpportunity]:
        """
        Analyze with order book depth consideration.
        Calculates actual executable price for target position size.
        """
        opp = await self.analyze(market)
        if not opp:
            return None

        # Get order book depth for both tokens
        yes_token = opp.tokens[0]
        no_token = opp.tokens[1]

        yes_depth = await self.clob.analyze_depth(yes_token.token_id, target_size)
        no_depth = await self.clob.analyze_depth(no_token.token_id, target_size)

        yes_exec = yes_depth.get("executable_price")
        no_exec = no_depth.get("executable_price")

        if yes_exec is None or no_exec is None:
            # Insufficient liquidity for target size
            opp.max_executable_size = min(
                yes_depth.get("available_size", 0),
                no_depth.get("available_size", 0),
            )
            return opp

        # Recalculate with executable prices
        total_exec_cost = yes_exec + no_exec
        if total_exec_cost >= 1.0:
            # No longer profitable at target size
            opp.max_executable_size = 0
            return None

        # Update with execution-adjusted values
        opp.total_cost = total_exec_cost
        opp.profit = 1.0 - total_exec_cost
        opp.profit_percent = (opp.profit / total_exec_cost) * 100
        opp.max_executable_size = target_size
        opp.estimated_slippage = max(
            yes_depth.get("slippage_percent", 0) or 0,
            no_depth.get("slippage_percent", 0) or 0,
        )

        return opp
