"""
NegRisk Arbitrage Strategy
Detects when sum of all YES prices < $1.00 in multi-outcome markets

Paper reference: $29M extracted from NegRisk arbitrage (largest source)

Polymarket Implementation:
- NegRisk markets are grouped under "events"
- Each outcome is a separate binary market (YES/NO)
- E.g., "Who wins election?" → 10 separate "Will X win?" markets
- Arbitrage: Sum of all YES prices across markets < $1
"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime

from .base import Strategy
from ..models import Market, ArbitrageOpportunity, ArbitrageType, MarketType, Token
from ..api.clob import CLOBClient
from ..config import config


class NegRiskArbitrageStrategy(Strategy):
    """
    NegRisk (multi-outcome) market arbitrage.

    In Polymarket, NegRisk is implemented as multiple binary markets
    under one event. Each market is "Will [candidate] win?" with YES/NO.

    Exactly ONE YES will resolve to $1.00, all others to $0.
    If sum of all YES best asks < $1.00, buying all YES guarantees profit.

    Example (5 candidates, each a separate market):
        "Will A win?" YES: $0.25
        "Will B win?" YES: $0.22
        "Will C win?" YES: $0.18
        "Will D win?" YES: $0.15
        "Will E win?" YES: $0.12
        Total YES:        $0.92
        Profit:           $0.08 (8.7%)

    Paper finding: "NO 매수" strategy was most profitable ($17.3M)
    When sum of YES > $1, buying all NO is profitable.
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
        return "negrisk_arbitrage"

    async def analyze(self, market: Market) -> Optional[ArbitrageOpportunity]:
        """Analyze a single NegRisk market (legacy, for multi-token markets)"""
        # This is kept for backwards compatibility
        # Real NegRisk analysis happens in analyze_event
        if market.market_type != MarketType.NEGRISK or len(market.tokens) < 3:
            return None
        return None

    async def analyze_event(
        self, event: Dict[str, Any]
    ) -> Optional[ArbitrageOpportunity]:
        """
        Analyze a NegRisk event (multiple markets under one event).

        This is the main method for Polymarket NegRisk arbitrage.
        """
        markets: List[Market] = event.get("markets", [])
        if len(markets) < 3:
            return None

        # Get YES token IDs (first token of each market)
        yes_tokens = []
        for m in markets:
            if m.tokens and len(m.tokens) >= 1:
                yes_tokens.append((m, m.tokens[0]))  # (market, YES token)

        if len(yes_tokens) < 3:
            return None

        # Get all YES prices concurrently
        token_ids = [t.token_id for _, t in yes_tokens]
        prices = await self.clob.get_prices_batch(token_ids, side="buy")

        # Calculate total YES cost
        total_yes = 0.0
        valid_tokens = []

        for market, token in yes_tokens:
            price = prices.get(token.token_id)
            if price is None or price <= 0:
                continue
            total_yes += price
            token.price = price
            token.best_ask = price
            token.outcome = market.question[:30]  # Use market question as outcome name
            valid_tokens.append(token)

        if len(valid_tokens) < 3:
            return None

        # Check for underpriced (sum < $1 → buy all YES)
        if total_yes < 1.0:
            profit = 1.0 - total_yes
            profit_percent = (profit / total_yes) * 100
            total_liquidity = event.get("total_liquidity", 0)

            if not self.meets_thresholds(
                profit_percent, total_liquidity, self.min_profit, self.min_liquidity
            ):
                return None

            return ArbitrageOpportunity(
                market_id=event.get("event_id", ""),
                condition_id="",
                question=f"[NegRisk] {event.get('title', 'Unknown Event')}",
                url=f"https://polymarket.com/event/{event.get('slug', '')}",
                category="negrisk",
                arb_type=ArbitrageType.NEGRISK_UNDERPRICED,
                market_type=MarketType.NEGRISK,
                total_cost=total_yes,
                profit=profit,
                profit_percent=profit_percent,
                tokens=valid_tokens,
                liquidity=total_liquidity,
                timestamp=datetime.now(),
            )

        # Check for overpriced (sum > $1 → buy all NO)
        elif total_yes > 1.0:
            # Get NO prices
            no_tokens = []
            for m in markets:
                if m.tokens and len(m.tokens) >= 2:
                    no_tokens.append((m, m.tokens[1]))  # NO is second token

            no_ids = [t.token_id for _, t in no_tokens]
            no_prices = await self.clob.get_prices_batch(no_ids, side="buy")

            total_no = 0.0
            valid_no_tokens = []

            for market, token in no_tokens:
                price = no_prices.get(token.token_id)
                if price is None or price <= 0:
                    continue
                total_no += price
                token.price = price
                token.best_ask = price
                token.outcome = f"NO: {market.question[:25]}"
                valid_no_tokens.append(token)

            # If we can buy all NO for < $1, that's arbitrage
            # (Exactly one YES wins → all but one NO wins → we get $N-1)
            # But the math is different: we need sum of NO < (N-1) where N = outcomes
            n_outcomes = len(valid_no_tokens)
            if n_outcomes >= 3 and total_no < (n_outcomes - 1):
                profit = (n_outcomes - 1) - total_no
                profit_percent = (profit / total_no) * 100
                total_liquidity = event.get("total_liquidity", 0)

                if profit_percent >= self.min_profit and total_liquidity >= self.min_liquidity:
                    return ArbitrageOpportunity(
                        market_id=event.get("event_id", ""),
                        condition_id="",
                        question=f"[NegRisk NO] {event.get('title', 'Unknown Event')}",
                        url=f"https://polymarket.com/event/{event.get('slug', '')}",
                        category="negrisk",
                        arb_type=ArbitrageType.NEGRISK_OVERPRICED,
                        market_type=MarketType.NEGRISK,
                        total_cost=total_no,
                        profit=profit,
                        profit_percent=profit_percent,
                        tokens=valid_no_tokens,
                        liquidity=total_liquidity,
                        timestamp=datetime.now(),
                    )

        return None

    async def analyze_batch(
        self, markets: List[Market]
    ) -> List[ArbitrageOpportunity]:
        """Analyze multiple NegRisk markets (legacy)"""
        return []  # Use analyze_events_batch instead

    async def analyze_events_batch(
        self, events: List[Dict[str, Any]]
    ) -> List[ArbitrageOpportunity]:
        """Analyze multiple NegRisk events concurrently"""
        tasks = [self.analyze_event(e) for e in events]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        opportunities = []
        for result in results:
            if isinstance(result, ArbitrageOpportunity):
                opportunities.append(result)

        opportunities.sort(key=lambda x: x.profit_percent, reverse=True)
        return opportunities
