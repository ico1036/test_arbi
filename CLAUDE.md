# Polymarket Arbitrage Bot - Project Context

## 🎯 Project Overview

This is a **Polymarket Arbitrage Detection System v3.2** - a real-time WebSocket-based trading tool designed to identify risk-free arbitrage opportunities in prediction markets.

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
├── src/polyarb/                     # v3.2 - WebSocket + Paper Trading
│   ├── api/
│   │   ├── gamma.py                 # Market/event discovery (REST)
│   │   ├── clob.py                  # Price/orderbook (REST for init)
│   │   └── websocket.py             # Real-time streaming + RealtimeArbitrageDetector
│   ├── paper_trading/               # Paper Trading PoC
│   │   ├── __init__.py              # Module exports
│   │   ├── models.py                # Position, Trade, TradingSession
│   │   └── engine.py                # PaperTradingEngine
│   ├── scanner.py                   # WebSocket-based scanner (run method only)
│   ├── alerts.py                    # Discord/Telegram
│   ├── models.py                    # Data models
│   ├── config.py                    # Configuration
│   └── main.py                      # CLI entry point (paper subcommand)
│
├── tests/                           # Test suite (76 tests)
│   ├── conftest.py                  # Minimal fixtures
│   ├── test_models.py               # Data model tests (21 tests)
│   ├── test_websocket_detection.py  # WebSocket detection tests (27 tests)
│   └── test_paper_trading.py        # Paper trading tests (28 tests)
│
├── README.md                        # Documentation
├── CLAUDE.md                        # This file - AI context
├── pyproject.toml                   # Project dependencies (uv)
├── .mcp.json                        # MCP server configuration
├── .env                             # Environment variables (create this)
└── arbitrage_opportunities.csv      # Auto-generated log file
```

### Version Comparison

| Version | Architecture | Detection Latency | Features |
|---------|--------------|-------------------|----------|
| v1.0 | Sync REST | ~5 min/scan | Basic detection |
| v2.0 | Sync REST | ~5 min/scan | + Alerts, logging |
| v3.0 | Async REST | ~15 sec/scan | + NegRisk, depth analysis |
| v3.1 | WebSocket | <100ms | Real-time streaming |
| **v3.2** | **WebSocket** | **<100ms** | + Paper Trading PoC |

---

## 🔧 Technical Architecture

### APIs Used (No Authentication Required)

| API | Endpoint | Purpose |
|-----|----------|---------|
| **Gamma API** | `https://gamma-api.polymarket.com/markets` | Market discovery (REST) |
| **CLOB API** | `https://clob.polymarket.com` | Initial price fetch (REST) |
| **WebSocket** | `wss://ws-subscriptions-clob.polymarket.com` | Real-time price streaming |

### Key Classes

```python
# Real-time State Tracking (websocket.py)
@dataclass
class MarketState:
    """Tracks binary market state for arbitrage detection"""
    market_id: str
    yes_token_id: str
    no_token_id: str
    yes_ask: Optional[float]
    no_ask: Optional[float]
    yes_bid: Optional[float]
    no_bid: Optional[float]

    def check_underpriced(min_profit) -> Optional[Dict]
    def check_overpriced(min_profit) -> Optional[Dict]

@dataclass
class NegRiskEventState:
    """Tracks multi-outcome event state"""
    event_id: str
    yes_prices: Dict[str, float]  # token_id -> price

    def check_underpriced(min_profit) -> Optional[Dict]

class RealtimeArbitrageDetector:
    """Main detection engine - processes WebSocket messages"""
    def register_binary_market(...)
    def register_negrisk_event(...)
    def process_message(message) -> List[Dict]  # Returns opportunities

# Scanner (scanner.py)
class ArbitrageScanner:
    async def run()  # WebSocket-based real-time detection
```

### Core Flow

```python
async def run():
    # 1. REST: Fetch markets via Gamma API
    markets = await gamma.get_all_markets()
    events = await gamma.get_negrisk_events()

    # 2. REST: Get initial prices via CLOB API
    prices = await clob.get_prices_batch(token_ids)

    # 3. Register with detector
    detector = RealtimeArbitrageDetector(min_profit, min_liquidity)
    for market in markets:
        detector.register_binary_market(...)

    # 4. WebSocket: Stream price updates
    async with WebSocketClient() as ws:
        await ws.subscribe(token_ids)
        async for message in ws.listen():
            opportunities = detector.process_message(message)
            # Display/alert on new opportunities
```

---

## ⚙️ Configuration

### Default Parameters
```python
MIN_PROFIT_PERCENT = 1.0    # Minimum 1% profit threshold
MIN_LIQUIDITY = 1000        # Minimum $1,000 market liquidity
MAX_MARKETS = 500           # Markets to monitor
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
python -m polyarb                          # Real-time scanning
python -m polyarb --min-profit 3.0         # 3%+ opportunities only
python -m polyarb --min-liquidity 10000    # $10K+ liquidity only
python -m polyarb --no-alerts              # Disable alerts
python -m polyarb --no-log                 # Disable CSV logging
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

**Recommended Margin**: 3%+ for safety after potential fees

---

## 🚀 Quick Start

### Installation
```bash
# Setup with uv
uv sync

# Run real-time scanner
uv run python -m polyarb

# Run with custom thresholds
uv run python -m polyarb --min-profit 3 --min-liquidity 5000
```

### Run Tests
```bash
uv run pytest                               # All 48 tests
uv run pytest tests/test_websocket_detection.py  # WebSocket tests only
uv run pytest tests/test_models.py          # Model tests only
```

---

## ⚠️ Risk Factors

1. **Execution Risk**: Non-atomic trades - one leg may fail
2. **Latency**: Top arbitragers are bots (Top 1: $2M, 4,049 trades)
3. **Liquidity**: Large orders cause slippage
4. **Fee Changes**: Currently 0%, may change

---

## 🎯 Development Roadmap

### Phase 1: Detection (✅ Complete)
- [x] Gamma API integration
- [x] CLOB order book parsing
- [x] Binary UNDERPRICED detection
- [x] Binary OVERPRICED detection
- [x] NegRisk UNDERPRICED detection
- [x] Discord/Telegram alerts
- [x] CSV logging
- [x] **WebSocket real-time detection (<100ms)**
- [x] Test suite (48 tests)

### Phase 2: Execution (📋 Planned)
- [ ] py-clob-client integration
- [ ] Order management system
- [ ] Position tracking
- [ ] P&L reporting

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

---

## 🧪 Testing Principles

### Core Philosophy
**테스트는 클라이언트 관점에서 "이걸 기대하면 이게 나와야 한다"를 검증한다.**

### Rules

1. **테스트 실패 시 코드를 의심하라**
   - 테스트가 실패하면 테스트를 수정하지 말고, 코드가 기대와 맞는지 먼저 확인
   - 예: "잔고 $50인데 $100 거래하면 거절해야 한다" → 테스트가 맞고 코드가 틀린 것

2. **Mock 최소화**
   - 실제 동작을 테스트하라
   - Mock은 외부 의존성(API 호출 등)에만 사용

3. **엣지케이스 커버**
   - 경계 조건, 예외 상황을 반드시 테스트
   - 예: 잔고 0, 유동성 0, 빈 리스트 등

4. **쓸모없는 테스트 금지**
   - getter/setter 단순 테스트 불필요
   - 의미 있는 비즈니스 로직만 테스트

### Example

```python
# ❌ Bad: 테스트를 코드에 맞춤
def test_insufficient_balance(self):
    # "어차피 max_position_pct로 줄어드니까 통과하겠지"
    ...

# ✅ Good: 코드를 기대에 맞춤
def test_insufficient_balance(self):
    """잔고 $50인데 $100 거래 요청하면 거절해야 한다"""
    engine = PaperTradingEngine(initial_balance=50, position_size=100)
    success = engine.execute_opportunity(opportunity)
    assert success is False  # 이게 실패하면 코드가 틀린 것
```

---

*Last updated: 2025-01-03*
*v3.2 - Paper Trading PoC added*
*Strategy Advisor: `.claude/commands/arb-advisor.md`*
