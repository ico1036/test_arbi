#!/usr/bin/env python3
"""
Polymarket Arbitrage Bot v3.0
=============================
High-performance arbitrage detection for Polymarket.

Features:
- Async REST API for 9x faster scanning
- WebSocket support for real-time updates
- Binary (YES/NO) and NegRisk (multi-outcome) arbitrage
- Order book depth analysis
- Discord/Telegram alerts

Usage:
    python -m polyarb                          # Default scan
    python -m polyarb --once                   # Single scan
    python -m polyarb --min-profit 3.0         # 3%+ opportunities only
    python -m polyarb --min-liquidity 10000    # $10K+ liquidity only
    python -m polyarb --interval 5             # 5 second intervals
    python -m polyarb --hybrid                 # REST + WebSocket mode
"""
import argparse
import asyncio
import sys

from .config import config
from .scanner import ArbitrageScanner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Polymarket Arbitrage Scanner v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m polyarb                          # Continuous scanning
    python -m polyarb --once                   # Single scan
    python -m polyarb --min-profit 2 --min-liquidity 5000
    python -m polyarb --hybrid                 # REST + WebSocket mode

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
        "--interval",
        type=int,
        default=config.arbitrage.scan_interval,
        help=f"Scan interval in seconds (default: {config.arbitrage.scan_interval})",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=config.arbitrage.max_markets,
        help=f"Maximum markets to scan (default: {config.arbitrage.max_markets})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single scan and exit",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Hybrid mode: REST scan + WebSocket monitoring",
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

    # Run appropriate mode
    if args.once:
        await scanner.run_once()
    elif args.hybrid:
        await scanner.run_hybrid()
    else:
        await scanner.run_continuous(interval=args.interval)


def main():
    """Entry point"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
