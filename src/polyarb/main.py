#!/usr/bin/env python3
"""
Polymarket Arbitrage Bot v3.2
=============================
Real-time WebSocket-based arbitrage detection for Polymarket.

Features:
- WebSocket streaming for <100ms detection latency
- Binary (YES/NO) and NegRisk (multi-outcome) arbitrage
- Discord/Telegram alerts
- Paper trading mode for strategy validation

Usage:
    python -m polyarb                          # Real-time scanning
    python -m polyarb --min-profit 3.0         # 3%+ opportunities only
    python -m polyarb paper --balance 10000    # Paper trading mode
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime

from .config import config
from .scanner import ArbitrageScanner
from .paper_trading import PaperTradingEngine, TradingMode, PRESETS, get_mode_comparison, SummaryChart


def parse_args():
    parser = argparse.ArgumentParser(
        description="Polymarket Arbitrage Scanner v3.2 (WebSocket)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m polyarb                          # Real-time scanning
    python -m polyarb --min-profit 2 --min-liquidity 5000
    python -m polyarb paper --balance 10000    # Paper trading

Paper-based recommendations:
    - Sports markets: Higher frequency of opportunities
    - Politics markets: Larger profit potential
    - Target 3%+ profit for safer margins after fees
        """,
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Paper trading subcommand
    paper_parser = subparsers.add_parser("paper", help="Paper trading mode")
    paper_parser.add_argument(
        "--mode",
        type=str,
        choices=["conservative", "moderate", "aggressive"],
        help="Preset trading mode (overrides other settings)",
    )
    paper_parser.add_argument(
        "--balance",
        type=float,
        default=10000,
        help="Initial virtual balance (default: 10000)",
    )
    paper_parser.add_argument(
        "--size",
        type=float,
        default=100,
        help="Position size per trade (default: 100)",
    )
    paper_parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Duration in seconds (0 = unlimited, default: 0)",
    )
    paper_parser.add_argument(
        "--min-profit",
        type=float,
        default=None,
        help=f"Minimum profit %% (default: {config.arbitrage.min_profit_percent})",
    )
    paper_parser.add_argument(
        "--min-liquidity",
        type=float,
        default=None,
        help=f"Minimum liquidity $ (default: {config.arbitrage.min_liquidity})",
    )
    paper_parser.add_argument(
        "--failure-rate",
        type=float,
        default=0.0,
        help="Simulated execution failure rate 0-1 (default: 0)",
    )
    paper_parser.add_argument(
        "--latency",
        type=int,
        default=0,
        help="Simulated latency in ms (default: 0)",
    )

    # Main scanner arguments
    parser.add_argument(
        "--min-profit",
        type=float,
        default=config.arbitrage.min_profit_percent,
        help=f"Minimum profit %% (default: {config.arbitrage.min_profit_percent})",
    )
    parser.add_argument(
        "--min-liquidity",
        type=float,
        default=config.arbitrage.min_liquidity,
        help=f"Minimum liquidity $ (default: {config.arbitrage.min_liquidity})",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=config.arbitrage.max_markets,
        help=f"Maximum markets to scan (default: {config.arbitrage.max_markets})",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Disable Discord/Telegram alerts",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Disable CSV logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )

    return parser.parse_args()


async def run_paper_trading(args):
    """Run paper trading mode"""
    from .api.gamma import GammaClient
    from .api.clob import CLOBClient
    from .api.websocket import RealtimeArbitrageDetector
    from .models import MarketType

    # Determine mode and settings
    mode = None
    if args.mode:
        mode = TradingMode(args.mode)
        settings = PRESETS[mode]
        min_profit = args.min_profit or settings.min_profit
        min_liquidity = args.min_liquidity or settings.min_liquidity
        position_size = settings.position_size
        failure_rate = settings.failure_rate
        latency_ms = settings.latency_ms
    else:
        min_profit = args.min_profit or config.arbitrage.min_profit_percent
        min_liquidity = args.min_liquidity or config.arbitrage.min_liquidity
        position_size = args.size
        failure_rate = args.failure_rate
        latency_ms = args.latency

    print()
    print("=" * 64)
    if mode:
        print(f"  PAPER TRADING MODE [{mode.value.upper()}]")
    else:
        print("  PAPER TRADING MODE (Custom)")
    print("=" * 64)
    print(f"  Initial Balance: ${args.balance:,.2f}")
    print(f"  Position Size: ${position_size:,.2f}")
    print(f"  Min Profit: {min_profit}%")
    print(f"  Min Liquidity: ${min_liquidity:,.0f}")
    if failure_rate > 0 or latency_ms > 0:
        print(f"  Simulation: failure={failure_rate*100:.0f}%, latency={latency_ms}ms")
    if args.duration > 0:
        print(f"  Duration: {args.duration}s")
    print("=" * 64)
    print()

    # Initialize paper trading engine
    engine = PaperTradingEngine(
        initial_balance=args.balance,
        position_size=position_size,
        mode=mode,
        failure_rate=failure_rate,
        latency_ms=latency_ms,
    )

    # Initialize detector
    detector = RealtimeArbitrageDetector(
        min_profit_percent=min_profit,
        min_liquidity=min_liquidity,
    )

    # Connect engine to detector
    def on_opportunity(opp):
        success = engine.execute_opportunity(opp)
        if success:
            arb_type = opp.get("type", "")
            profit_pct = opp.get("profit_percent", 0)
            question = opp.get("question", opp.get("title", ""))[:40]
            print(f"  [TRADE] {arb_type} | {profit_pct:.2f}% | {question}...")
            engine.print_status()

    detector.on_opportunity = on_opportunity

    # Fetch markets and register
    print("Fetching markets...")
    async with GammaClient() as gamma, CLOBClient() as clob:
        markets = await gamma.get_all_markets(limit=500)
        binary_markets = [m for m in markets if m.market_type == MarketType.BINARY]
        events = await gamma.get_negrisk_events(limit=100)

        print(f"  Binary markets: {len(binary_markets)}")
        print(f"  NegRisk events: {len(events)}")

        # Get prices for binary markets
        all_token_ids = []
        for market in binary_markets[:200]:
            if len(market.tokens) == 2:
                all_token_ids.extend([market.tokens[0].token_id, market.tokens[1].token_id])

        print(f"  Fetching prices for {len(all_token_ids)} tokens...")
        all_asks = await clob.get_prices_batch(all_token_ids, side='buy')
        all_bids = await clob.get_prices_batch(all_token_ids, side='sell')

        # Register binary markets
        for market in binary_markets[:200]:
            if len(market.tokens) != 2:
                continue
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

        print(f"\n  Registered {len(detector.binary_markets)} markets")
        print()

        # Initial scan for existing opportunities
        # Note: A market can be both underpriced (ask) and overpriced (bid) due to spread.
        # We pick the better opportunity (higher profit %).
        print("Scanning for initial opportunities...")
        initial_count = 0
        for state in detector.binary_markets.values():
            under = state.check_underpriced(min_profit)
            over = state.check_overpriced(min_profit)

            # Pick the better one if both exist
            if under and over:
                if under["profit_percent"] >= over["profit_percent"]:
                    engine.execute_opportunity(under)
                else:
                    engine.execute_opportunity(over)
                initial_count += 1
            elif under:
                engine.execute_opportunity(under)
                initial_count += 1
            elif over:
                engine.execute_opportunity(over)
                initial_count += 1

        print(f"  Found {initial_count} initial opportunities")
        engine.print_status()

        # If duration specified, run for that time
        if args.duration > 0:
            print(f"\nRunning for {args.duration} seconds...")
            await asyncio.sleep(args.duration)
        else:
            print("\nPress Ctrl+C to stop and see summary...")
            try:
                while True:
                    await asyncio.sleep(60)
                    engine.print_status()
            except asyncio.CancelledError:
                pass

    # Print final summary
    print("\n" + "=" * 64)
    print("  PAPER TRADING SESSION COMPLETE")
    print("=" * 64)
    engine.print_status()

    # Save summary (JSON + PNG)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # JSON
    summary = engine.get_summary()
    json_file = f"paper_trading_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(summary, f, indent=2)

    # PNG chart
    png_file = f"paper_trading_{timestamp}.png"
    chart = SummaryChart(engine)
    chart.save(png_file)

    print("\n  Results saved:")
    print(f"    {json_file}")
    print(f"    {png_file}")


async def main_async():
    args = parse_args()

    # Paper trading mode
    if args.command == "paper":
        await run_paper_trading(args)
        return

    # Update config
    config.arbitrage.max_markets = args.max_markets
    config.debug = args.debug

    # Create scanner
    scanner = ArbitrageScanner(
        min_profit_percent=args.min_profit,
        min_liquidity=args.min_liquidity,
        enable_alerts=not args.no_alerts,
        enable_logging=not args.no_log,
    )

    # Run real-time WebSocket scanner
    await scanner.run()


def main():
    """Entry point"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n  Session interrupted by user")
        print("  Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
