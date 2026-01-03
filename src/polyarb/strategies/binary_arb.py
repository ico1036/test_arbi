"""
Binary Arbitrage Strategy

Detects arbitrage opportunities in binary markets:
1. UNDERPRICED: YES + NO < $1.00 → Buy both, merge for $1
2. OVERPRICED:  YES + NO > $1.00 → Mint pair for $1, sell both
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
    Binary market arbitrage detection.

    Two strategies:

    1. UNDERPRICED (YES + NO < $1.00):
       - Buy YES and NO at market
       - Merge to redeem $1.00
       - Profit = $1.00 - (YES + NO)

       Example:
         YES ask: $0.48, NO ask: $0.46
         Total: $0.94, Profit: $0.06 (6.38%)

    2. OVERPRICED (YES + NO > $1.00):
       - Mint YES+NO pair for $1.00 (via CTF Exchange)
       - Sell both at market
       - Profit = (YES + NO) - $1.00

       Example:
         YES bid: $0.55, NO bid: $0.52
         Total: $1.07, Profit: $0.07 (6.54%)
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
        """
        Analyze a single binary market for both underpriced and overpriced opportunities.

        Returns the first opportunity found (underpriced checked first).
        """
        # Must be binary market with exactly 2 tokens
        if market.market_type != MarketType.BINARY or len(market.tokens) != 2:
            return None

        yes_token = market.tokens[0]
        no_token = market.tokens[1]

        # Check for UNDERPRICED first (YES + NO < $1)
        opp = await self._check_underpriced(market, yes_token, no_token)
        if opp:
            return opp

        # Check for OVERPRICED (YES + NO > $1)
        opp = await self._check_overpriced(market, yes_token, no_token)
        if opp:
            return opp

        return None

    async def _check_underpriced(
        self, market: Market, yes_token, no_token
    ) -> Optional[ArbitrageOpportunity]:
        """
        Check for underpriced opportunity: YES_ask + NO_ask < $1.00
        Strategy: Buy both at ask, merge for $1.00
        """
        # Get best ask prices (what we pay to buy)
        prices = await self.clob.get_prices_batch(
            [yes_token.token_id, no_token.token_id], side="buy"
        )

        yes_ask = prices.get(yes_token.token_id)
        no_ask = prices.get(no_token.token_id)

        if yes_ask is None or no_ask is None:
            return None
        if yes_ask <= 0 or no_ask <= 0:
            return None

        total_cost = yes_ask + no_ask

        # Need total < $1 for underpriced arbitrage
        if total_cost >= 1.0:
            return None

        profit = 1.0 - total_cost
        profit_percent = (profit / total_cost) * 100

        if not self.meets_thresholds(
            profit_percent, market.liquidity, self.min_profit, self.min_liquidity
        ):
            return None

        # Update token prices
        yes_token.price = yes_ask
        yes_token.best_ask = yes_ask
        no_token.price = no_ask
        no_token.best_ask = no_ask

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

    async def _check_overpriced(
        self, market: Market, yes_token, no_token
    ) -> Optional[ArbitrageOpportunity]:
        """
        Check for overpriced opportunity: YES_bid + NO_bid > $1.00
        Strategy: Mint pair for $1.00, sell both at bid
        """
        # Get best bid prices (what we receive when selling)
        prices = await self.clob.get_prices_batch(
            [yes_token.token_id, no_token.token_id], side="sell"
        )

        yes_bid = prices.get(yes_token.token_id)
        no_bid = prices.get(no_token.token_id)

        if yes_bid is None or no_bid is None:
            return None
        if yes_bid <= 0 or no_bid <= 0:
            return None

        total_value = yes_bid + no_bid

        # Need total > $1 for overpriced arbitrage
        if total_value <= 1.0:
            return None

        # Profit = sell proceeds - mint cost ($1)
        profit = total_value - 1.0
        profit_percent = (profit / 1.0) * 100  # Cost basis is $1 (mint cost)

        if not self.meets_thresholds(
            profit_percent, market.liquidity, self.min_profit, self.min_liquidity
        ):
            return None

        # Update token prices (using bid prices for overpriced)
        yes_token.price = yes_bid
        yes_token.best_bid = yes_bid
        no_token.price = no_bid
        no_token.best_bid = no_bid

        return ArbitrageOpportunity(
            market_id=market.market_id,
            condition_id=market.condition_id,
            question=market.question,
            url=market.url,
            category=market.category,
            arb_type=ArbitrageType.BINARY_OVERPRICED,
            market_type=MarketType.BINARY,
            total_cost=1.0,  # Mint cost is always $1
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
