"""
Unified arbitrage scanner
Real-time WebSocket-based arbitrage detection
"""
import asyncio
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import List, Set, Optional

from .config import config
from .models import ArbitrageOpportunity, MarketType
from .api.gamma import GammaClient
from .api.clob import CLOBClient
from .api.websocket import WebSocketClient, RealtimeArbitrageDetector
from .alerts import AlertManager


class ArbitrageScanner:
    """
    Real-time WebSocket-based arbitrage scanner.

    Features:
    - WebSocket streaming for real-time price updates (<100ms detection)
    - Initial REST fetch for market discovery
    - Both binary and NegRisk market support
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

    async def run(self):
        """
        Run real-time arbitrage detection.

        1. Fetch markets via REST API for discovery
        2. Subscribe to WebSocket for real-time price updates
        3. Detect arbitrage opportunities in <100ms
        """
        self._print_banner()
        print("⚡ Real-time WebSocket arbitrage detection\n")

        # Create detector
        detector = RealtimeArbitrageDetector(
            min_profit_percent=self.min_profit,
            min_liquidity=self.min_liquidity,
        )

        # Set up opportunity callback
        def on_opportunity(opp):
            self._display_ws_opportunity(opp)

        detector.on_opportunity = on_opportunity

        # Fetch markets and register with detector
        print("📊 Fetching markets...")
        async with GammaClient() as gamma, CLOBClient() as clob:
            # Get binary markets
            markets = await gamma.get_all_markets(limit=config.arbitrage.max_markets)
            binary_markets = [m for m in markets if m.market_type == MarketType.BINARY]

            # Get NegRisk events
            negrisk_events = await gamma.get_negrisk_events(limit=100)

            print(f"   Found {len(binary_markets)} binary markets")
            print(f"   Found {len(negrisk_events)} NegRisk events")

            # Collect all token IDs for batch price fetching
            print("\n⏳ Fetching initial prices (parallel)...")
            all_token_ids = []
            token_to_market_info = {}  # token_id -> (market, is_yes)

            for market in binary_markets:
                if len(market.tokens) != 2:
                    continue
                yes_token = market.tokens[0]
                no_token = market.tokens[1]
                all_token_ids.extend([yes_token.token_id, no_token.token_id])
                token_to_market_info[yes_token.token_id] = (market, True)
                token_to_market_info[no_token.token_id] = (market, False)

            # Batch fetch all prices at once
            all_asks = await clob.get_prices_batch(all_token_ids, side="buy")
            all_bids = await clob.get_prices_batch(all_token_ids, side="sell")

            # Register binary markets with fetched prices
            registered_markets = set()
            for token_id, (market, is_yes) in token_to_market_info.items():
                if market.market_id in registered_markets:
                    continue
                registered_markets.add(market.market_id)

                yes_token = market.tokens[0]
                no_token = market.tokens[1]

                detector.register_binary_market(
                    market_id=market.market_id,
                    question=market.question,
                    slug=market.slug,
                    liquidity=market.liquidity,
                    category=market.category,
                    yes_token_id=yes_token.token_id,
                    no_token_id=no_token.token_id,
                    yes_ask=all_asks.get(yes_token.token_id),
                    no_ask=all_asks.get(no_token.token_id),
                    yes_bid=all_bids.get(yes_token.token_id),
                    no_bid=all_bids.get(no_token.token_id),
                )

            # Collect NegRisk token IDs
            negrisk_token_ids = []
            for event in negrisk_events:
                for m in event.get("markets", []):
                    if len(m.tokens) >= 2:
                        negrisk_token_ids.append(m.tokens[0].token_id)

            # Batch fetch NegRisk prices
            if negrisk_token_ids:
                nr_asks = await clob.get_prices_batch(negrisk_token_ids, side="buy")
                nr_bids = await clob.get_prices_batch(negrisk_token_ids, side="sell")
            else:
                nr_asks, nr_bids = {}, {}

            # Register NegRisk events
            for event in negrisk_events:
                event_markets = []
                for m in event.get("markets", []):
                    if len(m.tokens) >= 2:
                        yes_token = m.tokens[0]
                        event_markets.append({
                            "market_id": m.market_id,
                            "yes_token_id": yes_token.token_id,
                            "question": m.question,
                            "yes_ask": nr_asks.get(yes_token.token_id),
                            "yes_bid": nr_bids.get(yes_token.token_id),
                        })

                detector.register_negrisk_event(
                    event_id=str(event.get("event_id", "")),
                    title=event.get("title", ""),
                    slug=event.get("slug", ""),
                    total_liquidity=event.get("total_liquidity", 0),
                    markets=event_markets,
                )

        # Get all token IDs to monitor
        token_ids = detector.get_all_token_ids()
        stats = detector.get_stats()

        print(f"\n✅ Registered:")
        print(f"   Binary markets: {stats['binary_markets']}")
        print(f"   NegRisk events: {stats['negrisk_events']}")
        print(f"   Total tokens: {stats['total_tokens']}")

        # Initial scan for opportunities with current prices
        print("\n🔍 Checking for initial opportunities...")
        initial_opps = 0
        for state in detector.binary_markets.values():
            opp = state.check_underpriced(self.min_profit)
            if opp:
                self._display_ws_opportunity(opp)
                initial_opps += 1
            opp = state.check_overpriced(self.min_profit)
            if opp:
                self._display_ws_opportunity(opp)
                initial_opps += 1

        for state in detector.negrisk_events.values():
            opp = state.check_underpriced(self.min_profit)
            if opp:
                self._display_ws_opportunity(opp)
                initial_opps += 1
            opp = state.check_overpriced(self.min_profit)
            if opp:
                self._display_ws_opportunity(opp)
                initial_opps += 1

        if initial_opps == 0:
            print("   No initial opportunities found")

        # Connect to WebSocket
        print(f"\n🔌 Connecting to WebSocket...")
        print(f"   Subscribing to {min(len(token_ids), 1000)} tokens...")
        print("\n⚡ Listening for real-time price updates... (Ctrl+C to stop)\n")

        message_count = 0
        last_stats_time = time.perf_counter()

        try:
            async with WebSocketClient() as ws:
                # Subscribe in batches (WebSocket may have limits)
                batch_size = 100
                for i in range(0, min(len(token_ids), 1000), batch_size):
                    batch = token_ids[i:i + batch_size]
                    if i == 0:
                        await ws.subscribe(batch)
                    else:
                        await ws.add_subscription(batch)

                async for message in ws.listen():
                    # Process message and detect opportunities
                    opportunities = detector.process_message(message)
                    message_count += 1

                    # Print stats periodically
                    current_time = time.perf_counter()
                    if current_time - last_stats_time >= 30:
                        stats = detector.get_stats()
                        print(f"\n📊 Stats: {stats['messages_processed']} messages, "
                              f"{stats['opportunities_found']} opportunities")
                        last_stats_time = current_time

        except KeyboardInterrupt:
            stats = detector.get_stats()
            print(f"\n\n👋 WebSocket scanner stopped")
            print(f"📊 Final stats:")
            print(f"   Messages processed: {stats['messages_processed']}")
            print(f"   Opportunities found: {stats['opportunities_found']}")

    def _display_ws_opportunity(self, opp: dict):
        """Display a WebSocket-detected opportunity"""
        opp_type = opp.get("type", "UNKNOWN")
        profit_pct = opp.get("profit_percent", 0)
        liquidity = opp.get("liquidity", 0)

        # Emoji based on type
        if "NEGRISK" in opp_type:
            emoji = "🎲"
        else:
            emoji = "🎯"

        if "OVERPRICED" in opp_type:
            action = "SELL"
        else:
            action = "BUY"

        print("\n" + "=" * 70)
        print(f"{emoji} {opp_type} [{action}] - {profit_pct:.2f}% profit")
        print("=" * 70)

        # Market/Event info
        if "question" in opp:
            print(f"📌 {opp['question'][:60]}...")
        elif "title" in opp:
            print(f"📌 {opp['title'][:60]}...")

        if "url" in opp:
            print(f"🔗 {opp['url']}")

        # Prices
        print("-" * 70)
        if "yes_ask" in opp and "no_ask" in opp:
            print(f"   YES ask: ${opp['yes_ask']:.4f}")
            print(f"   NO ask:  ${opp['no_ask']:.4f}")
            print(f"   Total:   ${opp.get('total_cost', 0):.4f}")
        elif "yes_bid" in opp and "no_bid" in opp:
            print(f"   YES bid: ${opp['yes_bid']:.4f}")
            print(f"   NO bid:  ${opp['no_bid']:.4f}")
            print(f"   Total:   ${opp.get('total_value', 0):.4f}")
        elif "prices" in opp:
            for token_id, price in list(opp["prices"].items())[:5]:
                print(f"   {token_id[:20]}... ${price:.4f}")
            if len(opp["prices"]) > 5:
                print(f"   ... and {len(opp['prices']) - 5} more")
            total = opp.get("total_cost", opp.get("total_value", 0))
            print(f"   Total: ${total:.4f}")

        print("-" * 70)
        print(f"💰 Profit: ${opp.get('profit', 0):.4f} ({profit_pct:.2f}%)")
        print(f"💧 Liquidity: ${liquidity:,.0f}")

        # Investment projection
        safe_invest = min(liquidity * 0.05, 5000)
        projected_profit = safe_invest * (profit_pct / 100)
        print(f"💡 ${safe_invest:,.0f} → ${projected_profit:.2f} profit")
        print("=" * 70)
        print(f"⏰ Detected at: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")

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
