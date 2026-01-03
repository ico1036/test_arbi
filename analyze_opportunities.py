#!/usr/bin/env python3
"""
Polymarket Arbitrage Analyzer
=============================
Advanced analysis tool for quant traders to analyze arbitrage opportunities.

Features:
- Statistical analysis of opportunities
- Risk-adjusted returns calculation
- Liquidity-weighted profit analysis
- Market efficiency metrics

Usage:
    python analyze_opportunities.py                    # Analyze current market
    python analyze_opportunities.py --top 20           # Show top 20 opportunities
    python analyze_opportunities.py --min-profit 3.0   # Filter by profit
    python analyze_opportunities.py --export           # Export to CSV
"""

import requests
import argparse
import time
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional
import json


# API Endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


@dataclass
class ArbitrageOpportunity:
    market_id: str
    question: str
    yes_price: float
    no_price: float
    total_cost: float
    profit: float
    profit_percent: float
    liquidity: float
    url: str
    yes_token_id: str
    no_token_id: str
    risk_adjusted_return: float = 0.0


def fetch_active_markets(limit: int = 500) -> List[dict]:
    """Fetch all active binary markets from Gamma API."""
    params = {
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "liquidity",
        "ascending": "false",
    }

    try:
        response = requests.get(f"{GAMMA_API}/markets", params=params, timeout=30)
        response.raise_for_status()
        markets = response.json()

        # Filter to binary markets with order books
        binary_markets = []
        for m in markets:
            clob_token_ids_raw = m.get("clobTokenIds", "[]")
            enable_ob = m.get("enableOrderBook", False)

            # Parse clobTokenIds (may be JSON string or list)
            if isinstance(clob_token_ids_raw, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids_raw)
                except:
                    clob_token_ids = []
            else:
                clob_token_ids = clob_token_ids_raw

            # Check for valid binary market (2 clobTokenIds = YES/NO)
            if enable_ob and len(clob_token_ids) == 2:
                # Build synthetic tokens from clobTokenIds
                # First token = YES, Second token = NO (Polymarket convention)
                m["tokens"] = [
                    {"token_id": clob_token_ids[0], "outcome": "YES"},
                    {"token_id": clob_token_ids[1], "outcome": "NO"},
                ]
                binary_markets.append(m)

        return binary_markets
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []


def get_best_ask_price(token_id: str) -> Optional[float]:
    """Get the best ask (lowest selling) price for a token."""
    try:
        params = {"token_id": token_id, "side": "buy"}
        response = requests.get(f"{CLOB_API}/price", params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return float(data.get("price", 0))
    except:
        pass
    return None


def analyze_market(market: dict) -> Optional[ArbitrageOpportunity]:
    """Analyze a single market for arbitrage opportunity."""
    tokens = market.get("tokens", [])
    if len(tokens) != 2:
        return None

    # Identify YES and NO tokens
    yes_token = next((t for t in tokens if t.get("outcome", "").upper() == "YES"), None)
    no_token = next((t for t in tokens if t.get("outcome", "").upper() == "NO"), None)

    if not yes_token or not no_token:
        return None

    yes_price = get_best_ask_price(yes_token["token_id"])
    no_price = get_best_ask_price(no_token["token_id"])

    if not yes_price or not no_price or yes_price <= 0 or no_price <= 0:
        return None

    total_cost = yes_price + no_price

    if total_cost >= 1.0:
        return None  # No arbitrage

    profit = 1.0 - total_cost
    profit_percent = (profit / total_cost) * 100
    liquidity = float(market.get("liquidity", 0))

    # Calculate risk-adjusted return (profit * sqrt(liquidity))
    risk_adjusted = profit_percent * (liquidity ** 0.5) / 1000

    slug = market.get("slug", market.get("id", ""))
    url = f"https://polymarket.com/event/{slug}"

    return ArbitrageOpportunity(
        market_id=market.get("id", ""),
        question=market.get("question", "")[:60] + "...",
        yes_price=yes_price,
        no_price=no_price,
        total_cost=total_cost,
        profit=profit,
        profit_percent=profit_percent,
        liquidity=liquidity,
        url=url,
        yes_token_id=yes_token["token_id"],
        no_token_id=no_token["token_id"],
        risk_adjusted_return=risk_adjusted,
    )


def calculate_statistics(opportunities: List[ArbitrageOpportunity]) -> dict:
    """Calculate aggregate statistics for opportunities."""
    if not opportunities:
        return {}

    profits = [o.profit_percent for o in opportunities]
    liquidities = [o.liquidity for o in opportunities]
    risk_adj = [o.risk_adjusted_return for o in opportunities]

    # Weighted average profit by liquidity
    total_liquidity = sum(liquidities)
    weighted_profit = sum(o.profit_percent * o.liquidity for o in opportunities) / total_liquidity

    return {
        "total_opportunities": len(opportunities),
        "avg_profit_percent": sum(profits) / len(profits),
        "max_profit_percent": max(profits),
        "min_profit_percent": min(profits),
        "median_profit_percent": sorted(profits)[len(profits) // 2],
        "weighted_avg_profit": weighted_profit,
        "total_liquidity_usd": total_liquidity,
        "avg_liquidity_usd": total_liquidity / len(opportunities),
        "best_risk_adjusted": max(risk_adj),
        "opportunities_above_2pct": sum(1 for p in profits if p >= 2.0),
        "opportunities_above_3pct": sum(1 for p in profits if p >= 3.0),
        "opportunities_above_5pct": sum(1 for p in profits if p >= 5.0),
    }


def print_analysis(opportunities: List[ArbitrageOpportunity], stats: dict, top_n: int = 20):
    """Print formatted analysis results."""
    print("\n" + "=" * 80)
    print("  POLYMARKET ARBITRAGE ANALYSIS")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    print("\n--- AGGREGATE STATISTICS ---")
    print(f"  Total Opportunities Found:     {stats.get('total_opportunities', 0)}")
    print(f"  Average Profit:                {stats.get('avg_profit_percent', 0):.2f}%")
    print(f"  Liquidity-Weighted Profit:     {stats.get('weighted_avg_profit', 0):.2f}%")
    print(f"  Max Profit:                    {stats.get('max_profit_percent', 0):.2f}%")
    print(f"  Median Profit:                 {stats.get('median_profit_percent', 0):.2f}%")
    print(f"  Total Market Liquidity:        ${stats.get('total_liquidity_usd', 0):,.0f}")
    print(f"  Avg Market Liquidity:          ${stats.get('avg_liquidity_usd', 0):,.0f}")
    print(f"  Opportunities >2%:             {stats.get('opportunities_above_2pct', 0)}")
    print(f"  Opportunities >3%:             {stats.get('opportunities_above_3pct', 0)}")
    print(f"  Opportunities >5%:             {stats.get('opportunities_above_5pct', 0)}")

    print("\n--- TOP OPPORTUNITIES BY RISK-ADJUSTED RETURN ---")
    print("-" * 80)
    print(f"{'#':>3} {'Profit':>7} {'Liq($K)':>8} {'Risk-Adj':>9} {'Market':<50}")
    print("-" * 80)

    # Sort by risk-adjusted return
    sorted_opps = sorted(opportunities, key=lambda x: x.risk_adjusted_return, reverse=True)[:top_n]

    for i, opp in enumerate(sorted_opps, 1):
        print(f"{i:>3} {opp.profit_percent:>6.2f}% {opp.liquidity/1000:>7.0f}K {opp.risk_adjusted_return:>8.2f} {opp.question:<50}")

    print("\n--- TOP OPPORTUNITIES BY PROFIT ONLY ---")
    print("-" * 80)

    sorted_by_profit = sorted(opportunities, key=lambda x: x.profit_percent, reverse=True)[:top_n]

    for i, opp in enumerate(sorted_by_profit, 1):
        print(f"{i:>3} {opp.profit_percent:>6.2f}% {opp.liquidity/1000:>7.0f}K {opp.risk_adjusted_return:>8.2f} {opp.question:<50}")

    print("\n--- PROFIT DISTRIBUTION ---")
    profit_buckets = {
        "0.1-0.5%": 0, "0.5-1%": 0, "1-2%": 0,
        "2-3%": 0, "3-5%": 0, ">5%": 0
    }

    for opp in opportunities:
        p = opp.profit_percent
        if p < 0.5:
            profit_buckets["0.1-0.5%"] += 1
        elif p < 1:
            profit_buckets["0.5-1%"] += 1
        elif p < 2:
            profit_buckets["1-2%"] += 1
        elif p < 3:
            profit_buckets["2-3%"] += 1
        elif p < 5:
            profit_buckets["3-5%"] += 1
        else:
            profit_buckets[">5%"] += 1

    for bucket, count in profit_buckets.items():
        bar = "█" * (count // 2)
        print(f"  {bucket:>8}: {count:>4} {bar}")

    print("\n" + "=" * 80)


def export_to_csv(opportunities: List[ArbitrageOpportunity], filename: str = "analysis_export.csv"):
    """Export opportunities to CSV file."""
    import csv

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "market_id", "question", "yes_price", "no_price", "total_cost",
            "profit", "profit_percent", "liquidity", "risk_adjusted_return",
            "yes_token_id", "no_token_id", "url"
        ])

        for opp in opportunities:
            writer.writerow([
                opp.market_id, opp.question, opp.yes_price, opp.no_price,
                opp.total_cost, opp.profit, opp.profit_percent, opp.liquidity,
                opp.risk_adjusted_return, opp.yes_token_id, opp.no_token_id, opp.url
            ])

    print(f"\nExported {len(opportunities)} opportunities to {filename}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Polymarket arbitrage opportunities")
    parser.add_argument("--top", type=int, default=20, help="Number of top opportunities to show")
    parser.add_argument("--min-profit", type=float, default=0.1, help="Minimum profit percentage")
    parser.add_argument("--min-liquidity", type=float, default=1000, help="Minimum liquidity USD")
    parser.add_argument("--export", action="store_true", help="Export results to CSV")
    parser.add_argument("--markets", type=int, default=500, help="Number of markets to scan")

    args = parser.parse_args()

    print(f"\nScanning {args.markets} markets...")
    print(f"Filters: min_profit={args.min_profit}%, min_liquidity=${args.min_liquidity:,.0f}")

    # Fetch markets
    markets = fetch_active_markets(args.markets)
    print(f"Found {len(markets)} binary markets with order books")

    # Analyze each market
    opportunities = []
    for i, market in enumerate(markets):
        if (i + 1) % 50 == 0:
            print(f"  Analyzed {i + 1}/{len(markets)} markets...")

        opp = analyze_market(market)
        if opp and opp.profit_percent >= args.min_profit and opp.liquidity >= args.min_liquidity:
            opportunities.append(opp)

    print(f"\nFound {len(opportunities)} arbitrage opportunities")

    if not opportunities:
        print("No opportunities found matching criteria.")
        return

    # Calculate statistics
    stats = calculate_statistics(opportunities)

    # Print analysis
    print_analysis(opportunities, stats, args.top)

    # Export if requested
    if args.export:
        export_to_csv(opportunities)


if __name__ == "__main__":
    main()
