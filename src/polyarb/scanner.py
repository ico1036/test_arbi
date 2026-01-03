"""
Unified arbitrage scanner
Combines async REST scanning with WebSocket monitoring
"""
import asyncio
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import List, Set, Optional

from .config import config
from .models import ArbitrageOpportunity, ScanResult, MarketType
from .api.gamma import GammaClient
from .api.clob import CLOBClient
from .api.websocket import WebSocketClient, PriceTracker
from .strategies import BinaryArbitrageStrategy, NegRiskArbitrageStrategy
from .alerts import AlertManager


class ArbitrageScanner:
    """
    High-performance arbitrage scanner.

    Features:
    - Async REST API for fast initial scans (~30s for 500 markets)
    - WebSocket streaming for real-time price updates
    - Both binary and NegRisk market support
    - Order book depth analysis
    - Deduplication and alerting
    """

    def __init__(
        self,
        min_profit_percent: float = None,
        min_liquidity: float = None,
        enable_alerts: bool = True,
        enable_logging: bool = True,
    ):
        self.min_profit = min_profit_percent or config.arbitrage.min_profit_percent
        self.min_liquidity = min_liquidity or config.arbitrage.min_liquidity
        self.enable_alerts = enable_alerts
        self.enable_logging = enable_logging

        # Track seen opportunities to avoid duplicate alerts
        self.seen_opportunities: Set[str] = set()
        self.opportunities_found = 0

        # Log file
        self.log_file = Path(config.log_file)
        if enable_logging and not self.log_file.exists():
            self._init_log_file()

    def _init_log_file(self):
        """Initialize CSV log file with headers"""
        with open(self.log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "market_id", "question", "arb_type", "market_type",
                "total_cost", "profit", "profit_percent", "liquidity",
                "category", "max_size", "url"
            ])

    def _log_opportunity(self, opp: ArbitrageOpportunity):
        """Log opportunity to CSV"""
        if not self.enable_logging:
            return

        with open(self.log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                opp.timestamp.isoformat(),
                opp.market_id,
                opp.question[:100],
                opp.arb_type.value,
                opp.market_type.value,
                opp.total_cost,
                opp.profit,
                opp.profit_percent,
                opp.liquidity,
                opp.category,
                opp.max_executable_size,
                opp.url,
            ])

    async def scan_once(self) -> ScanResult:
        """
        Perform a single scan of all markets.
        Uses async API for maximum speed.
        """
        start_time = time.perf_counter()
        result = ScanResult()

        print(f"\n🔍 Scanning markets... ({datetime.now().strftime('%H:%M:%S')})")

        async with GammaClient() as gamma, CLOBClient() as clob:
            # Fetch all markets and NegRisk events concurrently
            markets_task = gamma.get_all_markets(limit=config.arbitrage.max_markets)
            events_task = gamma.get_negrisk_events(limit=100)

            markets, negrisk_events = await asyncio.gather(
                markets_task, events_task, return_exceptions=True
            )

            if isinstance(markets, Exception):
                result.errors.append(f"Markets fetch error: {markets}")
                markets = []

            if isinstance(negrisk_events, Exception):
                result.errors.append(f"Events fetch error: {negrisk_events}")
                negrisk_events = []

            result.markets_scanned = len(markets)

            # Count by type
            binary_markets = [m for m in markets if m.market_type == MarketType.BINARY]
            result.binary_markets = len(binary_markets)
            result.negrisk_markets = len(negrisk_events)

            print(f"   📊 Found {len(markets)} binary markets + {len(negrisk_events)} NegRisk events")

            # Initialize strategies
            binary_strategy = BinaryArbitrageStrategy(
                clob, self.min_profit, self.min_liquidity
            )
            negrisk_strategy = NegRiskArbitrageStrategy(
                clob, self.min_profit, self.min_liquidity
            )

            # Run strategies concurrently
            binary_task = binary_strategy.analyze_batch(binary_markets)
            negrisk_task = negrisk_strategy.analyze_events_batch(negrisk_events)

            binary_opps, negrisk_opps = await asyncio.gather(
                binary_task, negrisk_task, return_exceptions=True
            )

            # Collect opportunities
            if isinstance(binary_opps, list):
                result.opportunities.extend(binary_opps)
            else:
                result.errors.append(f"Binary scan error: {binary_opps}")

            if isinstance(negrisk_opps, list):
                result.opportunities.extend(negrisk_opps)
                if negrisk_opps:
                    print(f"   🎲 Found {len(negrisk_opps)} NegRisk opportunities!")
            else:
                result.errors.append(f"NegRisk scan error: {negrisk_opps}")

        # Sort by profit
        result.opportunities.sort(key=lambda x: x.profit_percent, reverse=True)
        result.scan_duration = time.perf_counter() - start_time

        print(f"   ⏱️  Scan completed in {result.scan_duration:.2f}s")

        return result

    async def process_result(self, result: ScanResult) -> List[ArbitrageOpportunity]:
        """Process scan result: display, alert, log"""
        new_opportunities = []

        if not result.opportunities:
            print("   ❌ No arbitrage opportunities found")
            return new_opportunities

        print(f"\n   ✅ Found {len(result.opportunities)} opportunities!")

        async with AlertManager() as alerts:
            for opp in result.opportunities:
                is_new = opp.key not in self.seen_opportunities

                if is_new:
                    self.seen_opportunities.add(opp.key)
                    self.opportunities_found += 1
                    new_opportunities.append(opp)

                    # Display
                    self._display_opportunity(opp, is_new)

                    # Log
                    self._log_opportunity(opp)

                    # Alert
                    if self.enable_alerts:
                        await alerts.send_all(opp)

        return new_opportunities

    def _display_opportunity(self, opp: ArbitrageOpportunity, is_new: bool = True):
        """Display opportunity to console"""
        status = "🆕 NEW" if is_new else "📍 ACTIVE"
        type_emoji = "🎯" if opp.market_type == MarketType.BINARY else "🎲"

        print("\n" + "=" * 70)
        print(f"{type_emoji} {opp.arb_type.value.upper()} {status}")
        print("=" * 70)
        print(f"📌 {opp.question[:60]}...")
        print(f"🔗 {opp.url}")
        print("-" * 70)

        # Show token prices
        for token in opp.tokens[:6]:  # Max 6 tokens
            price_str = f"${token.price:.4f}" if token.price else "N/A"
            print(f"   {token.outcome:20} {price_str}")

        print("   " + "─" * 30)
        print(f"   Total Cost:  ${opp.total_cost:.4f}")
        print(f"   Settlement:  $1.0000")
        print("   " + "─" * 30)
        print(f"   💰 Profit:   ${opp.profit:.4f} ({opp.profit_percent:.2f}%)")
        print(f"   💧 Liquidity: ${opp.liquidity:,.0f}")
        print(f"   📊 Category: {opp.category or 'Unknown'}")

        if opp.max_executable_size > 0:
            print(f"   📈 Max Size: ${opp.max_executable_size:,.0f} @ {opp.estimated_slippage:.2f}% slippage")

        print("=" * 70)

        # Investment simulation
        print("\n   💡 Investment Projections:")
        for inv in [100, 500, 1000, 5000]:
            if inv <= opp.liquidity * 0.1:  # Max 10% of liquidity
                profit = opp.expected_profit(inv)
                print(f"      ${inv:,} → ${profit:.2f} profit")

    async def run_once(self) -> ScanResult:
        """Run a single scan and process results"""
        result = await self.scan_once()
        await self.process_result(result)
        return result

    async def run_continuous(self, interval: int = None):
        """Run continuous scanning with interval"""
        interval = interval or config.arbitrage.scan_interval
        self._print_banner()

        try:
            while True:
                await self.run_once()
                print(f"\n⏳ Next scan in {interval}s... (Ctrl+C to stop)")
                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\n\n👋 Scanner stopped")
            print(f"📊 Total opportunities found: {self.opportunities_found}")
            if self.enable_logging:
                print(f"📁 Log file: {self.log_file}")

    async def run_hybrid(self, initial_scan: bool = True):
        """
        Hybrid mode: Initial REST scan + WebSocket monitoring.
        Best of both worlds for speed and real-time updates.
        """
        self._print_banner()
        print("🔄 Running in HYBRID mode (REST + WebSocket)")

        # Initial scan with REST
        if initial_scan:
            result = await self.run_once()
            if not result.opportunities:
                print("   No initial opportunities. Monitoring for changes...")

        # Get all token IDs to monitor
        async with GammaClient() as gamma:
            markets = await gamma.get_all_markets(limit=config.arbitrage.max_markets)

        token_ids = []
        for m in markets:
            for t in m.tokens:
                token_ids.append(t.token_id)

        print(f"\n🔌 Connecting to WebSocket for {len(token_ids)} tokens...")

        # WebSocket monitoring
        price_tracker = PriceTracker()

        async with WebSocketClient() as ws:
            await ws.subscribe(token_ids[:100])  # WS limit

            async for message in ws.listen():
                await price_tracker.update(message)

                # Periodically re-scan with updated prices
                # (WebSocket updates are incremental)

    def _print_banner(self):
        """Print startup banner"""
        alerts = []
        if config.alerts.discord_webhook:
            alerts.append("Discord")
        if config.alerts.telegram_token:
            alerts.append("Telegram")

        print("\n" + "=" * 70)
        print("🤖 Polymarket Arbitrage Scanner v3.0")
        print("=" * 70)
        print(f"   Min Profit:    {self.min_profit}%")
        print(f"   Min Liquidity: ${self.min_liquidity:,}")
        print(f"   Max Markets:   {config.arbitrage.max_markets}")
        print(f"   Alerts:        {', '.join(alerts) if alerts else 'None (.env needed)'}")
        print(f"   Logging:       {'Enabled' if self.enable_logging else 'Disabled'}")
        print(f"   Strategies:    Binary + NegRisk")
        print("=" * 70)
        print("\n⚡ Starting scanner... (Ctrl+C to stop)\n")
