#!/usr/bin/env python3
"""
Polymarket Arbitrage Bot v3.1
=============================
Real-time WebSocket-based arbitrage detection for Polymarket.

Features:
- WebSocket streaming for <100ms detection latency
- Binary (YES/NO) and NegRisk (multi-outcome) arbitrage
- Discord/Telegram alerts

Usage:
    python -m polyarb                          # Real-time scanning
    python -m polyarb --min-profit 3.0         # 3%+ opportunities only
    python -m polyarb --min-liquidity 10000    # $10K+ liquidity only
"""
import argparse
import asyncio
import sys

from .config import config
from .scanner import ArbitrageScanner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Polymarket Arbitrage Scanner v3.1 (WebSocket)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m polyarb                          # Real-time scanning
    python -m polyarb --min-profit 2 --min-liquidity 5000

Paper-based recommendations:
    - Sports markets: Higher frequency of opportunities
    - Politics markets: Larger profit potential
    - Target 3%+ profit for safer margins after fees
        """,
    )

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


async def main_async():
    args = parse_args()

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
        print("\n👋 Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
