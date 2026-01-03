# Polymarket Arbitrage Bot - Project Context

## 🎯 Project Overview

This is a **Polymarket Arbitrage Detection System v3.0** - a high-performance quantitative trading tool designed to identify risk-free arbitrage opportunities in prediction markets.

**Based on academic paper findings:**
- NegRisk Arbitrage: $29M extracted (largest source)
- Single Condition Arbitrage: $15.26M extracted
- Combination Arbitrage: ~$95K (low ROI for complexity)

### Core Concepts

#### 1. Binary Arbitrage (Single Condition)
YES and NO shares always settle to exactly $1.00 combined. Two strategies exist:

**UNDERPRICED (YES_ask + NO_ask < $1.00):**
Buy both at market, merge to redeem $1.00.

```
Example:
  YES ask: $0.48
  NO ask:  $0.46
  ─────────────────
  Total:   $0.94
  Profit:  $0.06 (6.38% risk-free return)
```

**OVERPRICED (YES_bid + NO_bid > $1.00):**
Mint YES+NO pair for $1.00 via CTF Exchange, sell both at market.

```
Example:
  YES bid: $0.55
  NO bid:  $0.52
  ─────────────────
  Total:   $1.07
  Profit:  $0.07 (7.00% risk-free return)
```

#### 2. NegRisk Arbitrage (Multi-Outcome)
In events with multiple outcomes (e.g., "Who wins election?"), exactly ONE outcome resolves to $1.00.
Polymarket implements this as separate binary markets under one event.

```
Example (5 candidates):
  "Will A win?" YES: $0.25
  "Will B win?" YES: $0.22
  "Will C win?" YES: $0.18
  "Will D win?" YES: $0.15
  "Will E win?" YES: $0.12
  ─────────────────────────
  Total YES:        $0.92
  Profit:           $0.08 (8.7%)
```

---

## 📁 Project Structure

```
polymarket_arbi/
├── src/polyarb/                     # v3.0 - Async high-performance (45x faster)
│   ├── api/
│   │   ├── gamma.py                 # Market/event discovery (async)
│   │   ├── clob.py                  # Price/orderbook (parallel 50 req)
│   │   └── websocket.py             # Real-time streaming
│   ├── strategies/
│   │   ├── binary_arb.py            # Binary arbitrage (underpriced + overpriced)
│   │   └── negrisk_arb.py           # Event-based NegRisk detection
│   ├── scanner.py                   # Unified scanner
│   ├── alerts.py                    # Discord/Telegram
│   ├── models.py                    # Data models
│   ├── config.py                    # Configuration
│   └── main.py                      # CLI entry point
│
├── tests/                           # Test suite (78 tests)
│   ├── conftest.py                  # Fixtures & MockCLOBClient
│   ├── test_models.py               # Data model tests
│   ├── test_binary_arbitrage.py     # Binary strategy tests
│   ├── test_negrisk_arbitrage.py    # NegRisk strategy tests
│   └── test_edge_cases.py           # Edge case tests
│
├── README.md                        # Documentation
├── CLAUDE.md                        # This file - AI context
├── pyproject.toml                   # Project dependencies (uv)
├── .mcp.json                        # MCP server configuration
├── .env                             # Environment variables (create this)
├── .claude_config/                  # Claude AI configuration
│   └── settings.json                # Auto-approval for Python/uv commands
└── arbitrage_opportunities.csv      # Auto-generated log file
```

### Version Comparison

| Version | Architecture | 500 Markets Scan | Features |
|---------|--------------|------------------|----------|
| v1.0 | Sync REST | ~5 min | Basic detection |
| v2.0 | Sync REST | ~5 min | + Alerts, logging |
| **v3.0** | **Async REST** | **6.5 sec** | + NegRisk, WebSocket, depth analysis |

---

## 🔧 Technical Architecture

### APIs Used (No Authentication Required)

| API | Endpoint | Purpose |
|-----|----------|---------|
| **Gamma API** | `https://gamma-api.polymarket.com/markets` | Fetch active binary markets |
| **CLOB API** | `https://clob.polymarket.com` | Order book & pricing data |

### Key Classes

```python
# Data Model
@dataclass
class ArbitrageOpportunity:
    market_id: str
    question: str
    yes_price: float
    no_price: float
    total_cost: float
    profit_percent: float
    liquidity: float
    # ... more fields

# Main Bot
class PolymarketArbitrageBot:
    def fetch_active_markets()      # Get all binary markets
    def get_best_ask_price()        # Best ask from order book
    def check_arbitrage()           # Analyze single market
    def scan_all_markets()          # Full market sweep
    def run_continuous()            # Main loop
```

### Core Algorithm

```python
def check_arbitrage(market):
    yes_ask = get_best_ask_price(yes_token_id)
    no_ask = get_best_ask_price(no_token_id)

    total_cost = yes_ask + no_ask
    profit = 1.0 - total_cost
    profit_percent = (profit / total_cost) * 100

    if profit_percent >= MIN_PROFIT_PERCENT:
        if liquidity >= MIN_LIQUIDITY:
            return ArbitrageOpportunity(...)
    return None
```

---

## ⚙️ Configuration

### Default Parameters
```python
MIN_PROFIT_PERCENT = 1.0    # Minimum 1% profit threshold
MIN_LIQUIDITY = 1000        # Minimum $1,000 market liquidity
SCAN_INTERVAL = 10          # Seconds between scans (v2)
MAX_MARKETS = 500           # Markets to analyze per scan
```

### Environment Variables (.env)
```bash
# Optional - for Discord/Telegram alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### CLI Arguments
```bash
python polymarket_arbitrage_bot_v2.py \
    --min-profit 2.0 \      # Higher profit threshold
    --min-liquidity 5000 \  # Higher liquidity requirement
    --interval 5 \          # Faster scanning
    --once                  # Single run mode
```

---

## 💡 Arbitrage Economics

### Fee Structure (Polymarket)
- Trading Fee: **0.5%** (on winning outcomes only)
- Withdrawal Fee: Gas costs (Polygon network)

### Profitability Threshold
```
Gross Profit > 1.0%  →  Net Profit after fees ~0.5%
Gross Profit > 1.5%  →  Net Profit after fees ~1.0%
Gross Profit > 2.0%  →  Net Profit after fees ~1.5%
```

### Scale Considerations
- Small opportunities ($10-50 profit) may not be worth gas fees
- Large opportunities ($500+) attract competition, close fast
- Sweet spot: $50-200 profit range with >2% margin

### Optimal Position Sizing (Kelly Criterion)

For risk-free arbitrage with execution risk:
```
Optimal Bet Size = (p × b - q) / b

Where:
- p = Success probability (typically 0.7-0.9 for arbitrage)
- b = Profit rate (e.g., 0.06 for 6% arbitrage)
- q = Failure probability (1 - p)

Example (6% arbitrage, 80% success rate):
f* = (0.8 × 0.06 - 0.2) / 0.06 = -2.53

Negative result → Use fractional Kelly (10-25% of bankroll)
```

**Practical Position Sizing Guidelines:**

| Capital | Conservative (10%) | Moderate (20%) | Aggressive (30%) |
|---------|-------------------|-----------------|------------------|
| $1,000  | $100/trade       | $200/trade      | $300/trade       |
| $10,000 | $1,000/trade     | $2,000/trade    | $3,000/trade     |
| $50,000 | $5,000/trade     | $10,000/trade   | $15,000/trade    |

**Risk-Adjusted Sizing:**
```
Adjusted Size = Base Size × (Margin / 3%)

3% margin → 100% of base size
6% margin → 200% of base size
1.5% margin → 50% of base size
```

---

## 🚀 Quick Start

### Installation
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)

# Install dependencies
pip install requests python-dotenv

# Run bot
python polymarket_arbitrage_bot_v2.py
```

### Common Usage Patterns
```bash
# Conservative scan (higher thresholds)
python polymarket_arbitrage_bot_v2.py --min-profit 3.0 --min-liquidity 10000

# Quick test
python polymarket_arbitrage_bot_v2.py --once

# Aggressive monitoring (fast scan, low threshold)
python polymarket_arbitrage_bot_v2.py --min-profit 0.5 --interval 3

# Silent mode (no alerts)
python polymarket_arbitrage_bot_v2.py --no-alerts --no-log
```

---

## 📊 Output Formats

### Console Output
```
╔════════════════════════════════════════════════════════════════════╗
║                    🚨 ARBITRAGE OPPORTUNITY FOUND!                 ║
╠════════════════════════════════════════════════════════════════════╣
║ 📊 Market: Will Bitcoin reach $100k by 2024?                      ║
║ 💰 Profit: 2.54% ($25.40 per $1,000)                              ║
║ 💧 Liquidity: $45,230                                             ║
║ ⏳ Found at: 2024-12-31 14:30:22                                  ║
╚════════════════════════════════════════════════════════════════════╝
```

### CSV Log (arbitrage_opportunities.csv)
```csv
timestamp,market_id,question,yes_price,no_price,total_cost,profit,profit_percent,liquidity,url
2024-12-31T14:30:22,abc123,Will BTC...,0.48,0.46,0.94,0.06,6.38,45230,https://...
```

---

## 🔬 Advanced: Trade Execution

**Current Status**: Detection only (no auto-execution)

### For Automated Trading
```python
# Install official Python CLOB client
pip install py-clob-client

# Required for trading:
from py_clob_client.client import ClobClient

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,  # Polygon
    key="YOUR_PRIVATE_KEY",
    creds=ApiCreds(api_key, api_secret, passphrase)
)

# Place order
order = client.create_and_post_order(
    OrderArgs(
        token_id=token_id,
        price=0.48,
        size=100,
        side=BUY
    )
)
```

---

## ⚠️ Risk Factors

1. **Execution Risk**: Prices change; opportunity may disappear
2. **Liquidity Risk**: Large orders move prices
3. **Gas Fees**: Polygon network costs ~$0.01-0.10
4. **Platform Risk**: Polymarket terms of service
5. **Market Resolution**: Some markets have edge cases

---

## 🎯 Development Roadmap

### Phase 1: Detection (✅ Complete)
- [x] Gamma API integration
- [x] CLOB order book parsing
- [x] Arbitrage calculation engine
  - [x] Binary UNDERPRICED (YES_ask + NO_ask < $1)
  - [x] Binary OVERPRICED (YES_bid + NO_bid > $1)
  - [x] NegRisk UNDERPRICED (sum of YES < $1)
- [x] Discord/Telegram alerts
- [x] CSV logging
- [x] Comprehensive test suite (78 tests)

### Phase 2: Analysis (🔄 In Progress)
- [ ] Historical opportunity tracking
- [ ] Profit simulation with fees
- [ ] Market correlation analysis
- [ ] Liquidity depth analysis
- [ ] **Optimal betting strategy (Kelly Criterion)**
- [ ] **Position sizing calculator**
- [ ] **Risk-adjusted return analysis**

### Phase 3: Execution (📋 Planned)
- [ ] py-clob-client integration
- [ ] Order management system
- [ ] Position tracking
- [ ] P&L reporting

---

## 🧪 Testing Commands

```bash
# Single scan test
python polymarket_arbitrage_bot_v2.py --once --min-profit 0.1

# Verify API connectivity
python -c "import requests; print(requests.get('https://gamma-api.polymarket.com/markets?limit=1').status_code)"

# Check order book
python -c "import requests; r=requests.get('https://clob.polymarket.com/markets'); print(r.status_code, len(r.json()))"
```

---

## 📚 Reference

- **Polymarket Docs**: https://docs.polymarket.com
- **CLOB API Docs**: https://docs.polymarket.com/#clob-api
- **py-clob-client**: https://github.com/Polymarket/py-clob-client
- **Jane Street Reference**: Account88888 (historical arbitrage trader)

---

## 🔑 Key Insights for Quant Traders

1. **Speed matters**: Opportunities close within seconds
2. **Size matters**: Small opportunities have worse risk/reward
3. **Fees eat margins**: Target >1.5% gross for net profit
4. **Liquidity is king**: Low liquidity = high slippage
5. **Monitor continuously**: Best opportunities appear during volatility

---

## 📦 Project Files Reference

| File | Purpose |
|------|---------|
| `src/polyarb/` | v3.0 - Async high-performance implementation |
| `src/polyarb/strategies/binary_arb.py` | Binary arbitrage (underpriced + overpriced) |
| `src/polyarb/strategies/negrisk_arb.py` | NegRisk multi-outcome arbitrage |
| `tests/` | Comprehensive test suite (78 tests) |
| `CLAUDE.md` | This file - AI context document |
| `README.md` | Original documentation (Korean) |
| `pyproject.toml` | Project dependencies (uv) |
| `.env` | Environment variables (create this) |

---

## 🚀 Quick Commands

```bash
# Setup
uv sync

# v3.0 - Async high-performance (45x faster)
uv run python -m polyarb --once              # Single scan
uv run python -m polyarb --interval 10       # Continuous
uv run python -m polyarb --min-profit 3      # 3%+ only

# Run tests
uv run pytest                                # All 78 tests
uv run pytest tests/test_binary_arbitrage.py # Binary tests only
```

## ⚠️ Key Risk Factors (Paper-based)

1. **Execution Risk**: Non-atomic trades - one leg may fail
2. **Latency**: Top arbitragers are bots (Top 1: $2M, 4,049 trades)
3. **Liquidity**: Large orders cause slippage
4. **Fee Changes**: Currently 0%, may change

**Recommended Margin**: 3%+ for safety after potential fees

---

## 🧠 Strategy Advisor Subagent

For theoretical discussions about arbitrage strategies, use the `/arb-advisor` command.

**Usage:** `/arb-advisor <your question>`

**Example:**
```
/arb-advisor Should I focus on NegRisk or Binary markets?
/arb-advisor What's a realistic profit margin to target?
/arb-advisor Explain the execution risk in multi-leg trades
```

The advisor has deep knowledge of the academic paper "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets" (arXiv:2508.03474) including:
- $40M total extracted profit data
- Strategy-by-strategy breakdown
- Top trader statistics
- Risk factors and mitigations
- Market category analysis

---

*Last updated: 2025-01-03*
*v3.0 - Async architecture with 45.9x speed improvement*
*Phase 1 complete: Binary (underpriced + overpriced) & NegRisk detection*
*Strategy Advisor: `.claude/commands/arb-advisor.md`*
