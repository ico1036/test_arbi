# PRD: Polymarket Alpha Research Automation System

**Version:** 1.0
**Date:** 2025-01-05
**Author:** Quant Research Team
**Status:** Draft

---

## 1. Executive Summary

Polymarket 예측 시장에서 알파를 자동으로 발굴하고 검증하는 멀티 에이전트 시스템을 구축한다. Claude Agent SDK (Python)를 활용하여 6개의 전문 에이전트가 협업하는 워크플로우를 구현하며, 전략 템플릿 기반의 통제된 코드 생성으로 안정성과 확장성을 확보한다.

### 1.1 Goals

1. **알파 리서치 자동화**: 가설 생성 → 검증 → 구현 → 테스트 → 배포 사이클 자동화
2. **안전한 코드 생성**: Zone 기반 템플릿으로 에이전트의 코드 수정 범위 제한
3. **반복적 개선**: 성과 기반 자동 iteration으로 전략 품질 향상
4. **실시간 적용**: 기존 WebSocket 인프라와 통합하여 즉시 실행 가능

### 1.2 Non-Goals (v1.0)

- 실제 자금 거래 실행 (Paper Trading만 지원)
- 과거 오더북 데이터 기반 백테스트 (Forward Testing만 지원)
- 다중 거래소 지원 (Polymarket Only)

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                               │
│  CLI / API / Discord Bot                                            │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR AGENT                           │
│  - Parse user request                                                │
│  - Generate Goal & Execution Plan                                    │
│  - Coordinate agent workflow                                         │
│  - Handle iteration loops                                            │
│  - Claude Agent SDK: ClaudeSDKClient (main session)                 │
└─────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────┬───────────┼───────────┬─────────────┐
        ▼             ▼           ▼           ▼             ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   QUANT     │ │   QUANT     │ │  SENIOR     │ │ BACKTESTER  │
│ RESEARCHER  │ │ DEVELOPER   │ │ DEVELOPER   │ │             │
│             │ │             │ │             │ │             │
│ • Hypothesis│ │ • Implement │ │ • Code      │ │ • Forward   │
│ • EDA       │ │   in EDIT   │ │   Review    │ │   Testing   │
│ • Test Plan │ │   ZONE      │ │ • Safety    │ │ • Metrics   │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PORTFOLIO MANAGER AGENT                         │
│  - Performance evaluation                                            │
│  - Risk assessment                                                   │
│  - Iteration decision (DEPLOY / ITERATE / REJECT)                   │
│  - Next hypothesis generation                                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       STRATEGY TEMPLATES                             │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐          │
│  │ SignalGenerator│ │ArbitrageDetect │ │ MarketSelector │          │
│  │                │ │                │ │                │          │
│  │ FROZEN ██████  │ │ FROZEN ██████  │ │ FROZEN ██████  │          │
│  │ EDITABLE ░░░░  │ │ EDITABLE ░░░░  │ │ EDITABLE ░░░░  │          │
│  │ CONFIG ─────   │ │ CONFIG ─────   │ │ CONFIG ─────   │          │
│  └────────────────┘ └────────────────┘ └────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EXISTING INFRASTRUCTURE                           │
│  • WebSocket Client (실시간 오더북)                                  │
│  • Paper Trading Engine (시뮬레이션)                                 │
│  • Alert System (Discord/Telegram)                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Agent Communication Flow

```
User Request: "Order imbalance 기반 NegRisk 아비트라지 전략 개발해줘"
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR                                                         │
│                                                                      │
│ Goal: {                                                              │
│   "type": "composite",                                               │
│   "templates": ["SignalGenerator", "ArbitrageDetector"],            │
│   "hypothesis": "Order imbalance > 0.3 predicts favorable timing"   │
│ }                                                                    │
│                                                                      │
│ Plan: [                                                              │
│   {"agent": "quant_researcher", "task": "validate_hypothesis"},     │
│   {"agent": "quant_developer", "task": "implement_strategy"},       │
│   {"agent": "senior_developer", "task": "code_review"},             │
│   {"agent": "backtester", "task": "forward_test"},                  │
│   {"agent": "portfolio_manager", "task": "evaluate"}                │
│ ]                                                                    │
└─────────────────────────────────────────────────────────────────────┘
     │
     ▼ (Sequential execution with feedback loops)
```

---

## 3. Agent Specifications

### 3.1 Orchestrator Agent

**Role:** 전체 워크플로우 조율 및 에이전트 간 통신 관리

**Claude Agent SDK Configuration:**
```python
orchestrator_options = ClaudeAgentOptions(
    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    model="claude-sonnet-4-5",
    max_turns=50,
    max_budget_usd=10.0,
    allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
    mcp_servers={
        "workflow": workflow_mcp_server,
        "agents": agent_coordinator_mcp_server,
    },
    agents={
        "quant_researcher": RESEARCHER_CONFIG,
        "quant_developer": DEVELOPER_CONFIG,
        "senior_developer": REVIEWER_CONFIG,
        "backtester": BACKTESTER_CONFIG,
        "portfolio_manager": PM_CONFIG,
    }
)
```

**Input Schema:**
```python
@dataclass
class UserRequest:
    description: str           # 자연어 요청
    constraints: dict          # 제약 조건 (optional)
    target_metrics: dict       # 목표 지표 (optional)
```

**Output Schema:**
```python
@dataclass
class ExecutionPlan:
    goal: Goal
    steps: List[PlanStep]
    estimated_duration: str
    estimated_cost_usd: float
```

### 3.2 Quant Researcher Agent

**Role:** 가설 생성, EDA, 통계적 검증 설계

**System Prompt:**
```
You are a quantitative researcher specializing in prediction market arbitrage.
Your role is to:
1. Generate testable hypotheses based on market microstructure
2. Design validation experiments (primarily forward testing due to data limitations)
3. Define success criteria with specific metrics

CONSTRAINTS:
- Polymarket has NO historical orderbook data (only 1-min price history)
- Focus on forward testing designs
- Consider execution risk in multi-leg trades
```

**Tools:**
```python
researcher_tools = [
    "mcp__polymarket__get_price_history",
    "mcp__polymarket__get_market_metadata",
    "mcp__analysis__calculate_statistics",
    "Read", "Glob", "Grep"
]
```

**Output Schema:**
```python
@dataclass
class ResearchOutput:
    hypothesis: str
    validation_method: Literal["forward_test", "price_backtest", "synthetic"]
    test_duration_hours: int
    success_criteria: Dict[str, float]  # {"win_rate": 0.55, "sharpe": 1.0}
    preliminary_analysis: Optional[dict]
```

### 3.3 Quant Developer Agent

**Role:** EDITABLE ZONE 내에서 전략 로직 구현

**System Prompt:**
```
You are a quant developer implementing trading strategies.
Your role is to:
1. Implement strategy logic ONLY within EDITABLE ZONE markers
2. Use provided data structures and interfaces
3. Never modify FROZEN ZONE code

RULES:
- Only modify code between "# === EDITABLE ZONE ===" markers
- Use only allowed operations (arithmetic, comparison, list ops)
- Always return the correct output type as specified
- Handle edge cases (division by zero, empty lists, etc.)
```

**Hooks for Code Safety:**
```python
async def validate_code_modification(
    input_data: HookInput,
    tool_use_id: str,
    context: HookContext
) -> HookJSONOutput:
    """Block modifications outside EDITABLE ZONE."""
    if input_data["tool_name"] == "Edit":
        old_string = input_data["tool_input"].get("old_string", "")

        # Check if modifying frozen zone
        if "FROZEN ZONE" in old_string:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Cannot modify FROZEN ZONE code"
                }
            }
    return {}
```

**Output Schema:**
```python
@dataclass
class ImplementationOutput:
    template_name: str
    code_diff: str
    config: dict
    test_cases: List[dict]
```

### 3.4 Senior Developer Agent

**Role:** 코드 리뷰, 안전성 검증, 템플릿 규칙 준수 확인

**System Prompt:**
```
You are a senior developer reviewing trading strategy implementations.
Your role is to:
1. Verify FROZEN ZONE code is unmodified
2. Check for potential runtime errors
3. Validate template interface compliance
4. Ensure no forbidden operations are used

CHECKLIST:
□ FROZEN ZONE intact
□ Correct return types
□ Division by zero handled
□ Index bounds checked
□ No forbidden operations (import, exec, eval, open, __)
□ Config values within allowed ranges
```

**Tools:**
```python
reviewer_tools = [
    "mcp__code_analysis__check_syntax",
    "mcp__code_analysis__check_forbidden_ops",
    "mcp__code_analysis__validate_template",
    "Read"
]
```

**Output Schema:**
```python
@dataclass
class ReviewOutput:
    passed: bool
    issues: List[CodeIssue]
    suggestions: List[str]
    fixed_code: Optional[str]
```

### 3.5 Backtester Agent

**Role:** Forward Testing 실행, 성과 메트릭 계산

**System Prompt:**
```
You are a backtesting engineer running strategy simulations.
Your role is to:
1. Execute forward tests using Paper Trading engine
2. Collect performance metrics
3. Identify edge cases and failure modes

NOTE: Historical orderbook data is NOT available.
Use forward testing with live WebSocket data.
```

**Tools:**
```python
backtester_tools = [
    "mcp__paper_trading__run_forward_test",
    "mcp__paper_trading__get_performance_report",
    "mcp__paper_trading__get_trade_history",
    "mcp__metrics__calculate_sharpe",
    "mcp__metrics__calculate_drawdown",
]
```

**Output Schema:**
```python
@dataclass
class BacktestOutput:
    duration_hours: float
    total_trades: int
    metrics: PerformanceMetrics
    trade_log: List[Trade]
    failure_cases: List[dict]
```

### 3.6 Portfolio Manager Agent

**Role:** 성과 평가, 의사결정, 다음 iteration 계획

**System Prompt:**
```
You are a portfolio manager evaluating trading strategies.
Your role is to:
1. Compare performance against target metrics
2. Make deployment decisions (DEPLOY / ITERATE / REJECT)
3. Generate improvement hypotheses for next iteration

DECISION CRITERIA:
- DEPLOY: All targets met, risk acceptable
- ITERATE: Partial success, clear improvement path
- REJECT: Fundamental flaw, no viable path
```

**Output Schema:**
```python
@dataclass
class PMDecision:
    decision: Literal["DEPLOY", "ITERATE", "REJECT"]
    confidence: float
    reasoning: str
    next_iteration: Optional[IterationPlan]
    deployment_config: Optional[DeploymentConfig]
```

---

## 4. Strategy Templates

### 4.1 Template Design Principles

1. **Zone-Based Access Control:**
   - `FROZEN ZONE`: 데이터 파이프라인, 입출력 인터페이스, 기본 검증
   - `EDITABLE ZONE`: 전략 로직, 시그널 계산
   - `CONFIG ZONE`: 파라미터 값만 수정 가능

2. **Type Safety:**
   - 모든 입출력에 dataclass 사용
   - 런타임 타입 검증

3. **Error Isolation:**
   - EDITABLE ZONE 에러는 전체 시스템에 영향 없음
   - 자동 fallback to safe default

### 4.2 Template 1: SignalGenerator

**Purpose:** 방향성 시그널 생성 (Order Imbalance, Liquidity Vacuum, etc.)

```python
# ==================== FROZEN ZONE - DO NOT MODIFY ====================
from dataclasses import dataclass, field
from typing import Literal, Optional, List
from polyarb.models import OrderBook, MarketState

@dataclass
class Signal:
    """Output signal from SignalGenerator."""
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    strength: float      # 0.0 ~ 1.0
    confidence: float    # 0.0 ~ 1.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        assert 0.0 <= self.strength <= 1.0, "strength must be 0.0~1.0"
        assert 0.0 <= self.confidence <= 1.0, "confidence must be 0.0~1.0"


class SignalGenerator:
    """Base class for signal generation strategies."""

    REQUIRED_CONFIG = ["threshold"]
    OPTIONAL_CONFIG = {"lookback": 5, "min_volume": 1000}
    CONFIG_RANGES = {
        "threshold": (0.05, 0.95),
        "lookback": (1, 100),
        "min_volume": (0, 1000000),
    }

    def __init__(self, config: dict):
        self.config = {**self.OPTIONAL_CONFIG, **config}
        self._validate_config()

    def _validate_config(self):
        # Check required keys
        for key in self.REQUIRED_CONFIG:
            if key not in self.config:
                raise ValueError(f"Missing required config: {key}")

        # Check value ranges
        for key, (min_val, max_val) in self.CONFIG_RANGES.items():
            if key in self.config:
                val = self.config[key]
                if not (min_val <= val <= max_val):
                    raise ValueError(f"{key} must be between {min_val} and {max_val}")

    def process(self, market_state: MarketState, orderbook: OrderBook) -> Signal:
        """Process market data and generate signal. DO NOT OVERRIDE."""
        # Input validation
        if not orderbook or not orderbook.bids or not orderbook.asks:
            return Signal("NEUTRAL", 0.0, 0.0, {"reason": "no_orderbook"})

        if not market_state:
            return Signal("NEUTRAL", 0.0, 0.0, {"reason": "no_market_state"})

        # Call editable logic with error handling
        try:
            return self._calculate_signal(market_state, orderbook)
        except Exception as e:
            return Signal("NEUTRAL", 0.0, 0.0, {"error": str(e)})
# ==================== END FROZEN ZONE ====================


# ==================== EDITABLE ZONE - AGENT CAN MODIFY ====================
    def _calculate_signal(
        self,
        market_state: MarketState,
        orderbook: OrderBook
    ) -> Signal:
        """
        Calculate trading signal based on market data.

        AVAILABLE DATA:
        ---------------
        orderbook.bids: List[OrderLevel]  # Each has .price, .size
        orderbook.asks: List[OrderLevel]  # Each has .price, .size
        orderbook.best_bid: float
        orderbook.best_ask: float

        market_state.yes_bid: float
        market_state.yes_ask: float
        market_state.no_bid: float
        market_state.no_ask: float
        market_state.market_id: str

        self.config: dict  # Access config values

        MUST RETURN:
        ------------
        Signal(direction, strength, confidence, metadata)
        - direction: "LONG" | "SHORT" | "NEUTRAL"
        - strength: float 0.0 ~ 1.0
        - confidence: float 0.0 ~ 1.0
        - metadata: dict (optional info)

        EXAMPLE IMPLEMENTATION (Order Imbalance):
        -----------------------------------------
        """
        # Calculate order imbalance
        bid_volume = sum(level.size for level in orderbook.bids[:self.config["lookback"]])
        ask_volume = sum(level.size for level in orderbook.asks[:self.config["lookback"]])

        total_volume = bid_volume + ask_volume
        if total_volume < self.config["min_volume"]:
            return Signal("NEUTRAL", 0.0, 0.3, {"reason": "low_volume"})

        imbalance = (bid_volume - ask_volume) / total_volume
        threshold = self.config["threshold"]

        if imbalance > threshold:
            return Signal(
                direction="LONG",
                strength=min(abs(imbalance), 1.0),
                confidence=0.7,
                metadata={"imbalance": imbalance, "bid_vol": bid_volume, "ask_vol": ask_volume}
            )
        elif imbalance < -threshold:
            return Signal(
                direction="SHORT",
                strength=min(abs(imbalance), 1.0),
                confidence=0.7,
                metadata={"imbalance": imbalance, "bid_vol": bid_volume, "ask_vol": ask_volume}
            )

        return Signal("NEUTRAL", abs(imbalance), 0.5, {"imbalance": imbalance})
# ==================== END EDITABLE ZONE ====================


# ==================== CONFIG ZONE - PARAMETERS ONLY ====================
DEFAULT_CONFIG = {
    "threshold": 0.3,
    "lookback": 5,
    "min_volume": 1000,
}
# ==================== END CONFIG ZONE ====================
```

### 4.3 Template 2: ArbitrageDetector

**Purpose:** 아비트라지 기회 감지 (Binary, NegRisk, Cross-Event)

```python
# ==================== FROZEN ZONE - DO NOT MODIFY ====================
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Dict
from polyarb.models import MarketState

@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity."""
    type: Literal["BINARY_UNDER", "BINARY_OVER", "NEGRISK_UNDER", "NEGRISK_OVER", "CROSS_EVENT"]
    markets: List[str]           # Market IDs involved
    legs: List[Dict]             # Trade legs with token_id, side, price
    expected_profit_pct: float   # Expected profit percentage
    required_capital: float      # Capital needed
    risk_score: float            # 0.0 (safe) ~ 1.0 (risky)
    metadata: dict = field(default_factory=dict)


class ArbitrageDetector:
    """Base class for arbitrage detection strategies."""

    REQUIRED_CONFIG = ["min_profit_pct"]
    OPTIONAL_CONFIG = {"min_liquidity": 1000, "max_legs": 10}
    CONFIG_RANGES = {
        "min_profit_pct": (0.1, 50.0),
        "min_liquidity": (0, 1000000),
        "max_legs": (2, 20),
    }

    def __init__(self, config: dict):
        self.config = {**self.OPTIONAL_CONFIG, **config}
        self._validate_config()

    def _validate_config(self):
        for key in self.REQUIRED_CONFIG:
            if key not in self.config:
                raise ValueError(f"Missing required config: {key}")

        for key, (min_val, max_val) in self.CONFIG_RANGES.items():
            if key in self.config:
                val = self.config[key]
                if not (min_val <= val <= max_val):
                    raise ValueError(f"{key} must be between {min_val} and {max_val}")

    def detect(
        self,
        market_states: List[MarketState],
        event_id: Optional[str] = None
    ) -> List[ArbitrageOpportunity]:
        """Detect arbitrage opportunities. DO NOT OVERRIDE."""
        if not market_states:
            return []

        try:
            return self._find_opportunities(market_states, event_id)
        except Exception as e:
            return []
# ==================== END FROZEN ZONE ====================


# ==================== EDITABLE ZONE - AGENT CAN MODIFY ====================
    def _find_opportunities(
        self,
        market_states: List[MarketState],
        event_id: Optional[str]
    ) -> List[ArbitrageOpportunity]:
        """
        Find arbitrage opportunities in market data.

        AVAILABLE DATA:
        ---------------
        market_states: List[MarketState]
            Each MarketState has:
            - market_id: str
            - yes_token_id: str
            - no_token_id: str
            - yes_bid: Optional[float]
            - yes_ask: Optional[float]
            - no_bid: Optional[float]
            - no_ask: Optional[float]

        event_id: Optional[str]
            For NegRisk events, groups related markets

        self.config: dict
            - min_profit_pct: float
            - min_liquidity: float
            - max_legs: int

        MUST RETURN:
        ------------
        List[ArbitrageOpportunity]

        EXAMPLE IMPLEMENTATION (Binary Underpriced):
        --------------------------------------------
        """
        opportunities = []
        min_profit = self.config["min_profit_pct"] / 100

        for state in market_states:
            # Skip if missing prices
            if state.yes_ask is None or state.no_ask is None:
                continue

            # Binary Underpriced: YES_ask + NO_ask < 1.0
            total_ask = state.yes_ask + state.no_ask
            if total_ask < (1.0 - min_profit):
                profit_pct = (1.0 - total_ask) * 100

                opportunities.append(ArbitrageOpportunity(
                    type="BINARY_UNDER",
                    markets=[state.market_id],
                    legs=[
                        {"token_id": state.yes_token_id, "side": "BUY", "price": state.yes_ask},
                        {"token_id": state.no_token_id, "side": "BUY", "price": state.no_ask},
                    ],
                    expected_profit_pct=profit_pct,
                    required_capital=total_ask,
                    risk_score=0.2,  # Low risk for binary
                    metadata={"yes_ask": state.yes_ask, "no_ask": state.no_ask}
                ))

            # Binary Overpriced: YES_bid + NO_bid > 1.0
            if state.yes_bid is None or state.no_bid is None:
                continue

            total_bid = state.yes_bid + state.no_bid
            if total_bid > (1.0 + min_profit):
                profit_pct = (total_bid - 1.0) * 100

                opportunities.append(ArbitrageOpportunity(
                    type="BINARY_OVER",
                    markets=[state.market_id],
                    legs=[
                        {"token_id": state.yes_token_id, "side": "SELL", "price": state.yes_bid},
                        {"token_id": state.no_token_id, "side": "SELL", "price": state.no_bid},
                    ],
                    expected_profit_pct=profit_pct,
                    required_capital=1.0,  # Minting cost
                    risk_score=0.3,  # Slightly higher (need CTF)
                    metadata={"yes_bid": state.yes_bid, "no_bid": state.no_bid}
                ))

        return opportunities
# ==================== END EDITABLE ZONE ====================


# ==================== CONFIG ZONE - PARAMETERS ONLY ====================
DEFAULT_CONFIG = {
    "min_profit_pct": 1.0,
    "min_liquidity": 1000,
    "max_legs": 10,
}
# ==================== END CONFIG ZONE ====================
```

### 4.4 Template 3: MarketSelector

**Purpose:** 마켓 필터링 및 실행 최적화 (Time Decay, Volatility Regime, etc.)

```python
# ==================== FROZEN ZONE - DO NOT MODIFY ====================
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Dict
from datetime import datetime
from polyarb.models import Market, OrderBook

@dataclass
class MarketSelection:
    """Selected markets with execution plan."""
    markets: List[str]           # Selected market IDs
    priority_order: List[str]    # Execution priority (first = highest)
    execution_plan: Dict         # Strategy-specific execution details
    metadata: dict = field(default_factory=dict)


class MarketSelector:
    """Base class for market selection strategies."""

    REQUIRED_CONFIG = []
    OPTIONAL_CONFIG = {
        "max_markets": 50,
        "min_liquidity": 1000,
        "categories": None,  # None = all categories
    }
    CONFIG_RANGES = {
        "max_markets": (1, 500),
        "min_liquidity": (0, 1000000),
    }

    def __init__(self, config: dict):
        self.config = {**self.OPTIONAL_CONFIG, **config}
        self._validate_config()

    def _validate_config(self):
        for key in self.REQUIRED_CONFIG:
            if key not in self.config:
                raise ValueError(f"Missing required config: {key}")

        for key, (min_val, max_val) in self.CONFIG_RANGES.items():
            if key in self.config and self.config[key] is not None:
                val = self.config[key]
                if not (min_val <= val <= max_val):
                    raise ValueError(f"{key} must be between {min_val} and {max_val}")

    def select(
        self,
        markets: List[Market],
        orderbooks: Dict[str, OrderBook],
        current_time: datetime
    ) -> MarketSelection:
        """Select and prioritize markets. DO NOT OVERRIDE."""
        if not markets:
            return MarketSelection([], [], {})

        try:
            return self._select_markets(markets, orderbooks, current_time)
        except Exception as e:
            return MarketSelection([], [], {"error": str(e)})
# ==================== END FROZEN ZONE ====================


# ==================== EDITABLE ZONE - AGENT CAN MODIFY ====================
    def _select_markets(
        self,
        markets: List[Market],
        orderbooks: Dict[str, OrderBook],
        current_time: datetime
    ) -> MarketSelection:
        """
        Select and prioritize markets for monitoring.

        AVAILABLE DATA:
        ---------------
        markets: List[Market]
            Each Market has:
            - id: str
            - question: str
            - category: str
            - end_date: datetime
            - liquidity: float
            - volume_24h: float
            - tokens: List[Token]

        orderbooks: Dict[str, OrderBook]
            token_id -> OrderBook

        current_time: datetime
            Current UTC time

        self.config: dict
            - max_markets: int
            - min_liquidity: float
            - categories: Optional[List[str]]

        MUST RETURN:
        ------------
        MarketSelection(markets, priority_order, execution_plan, metadata)

        EXAMPLE IMPLEMENTATION (Time Decay + Category Filter):
        -----------------------------------------------------
        """
        selected = []

        for market in markets:
            # Category filter
            if self.config["categories"]:
                if market.category not in self.config["categories"]:
                    continue

            # Liquidity filter
            if market.liquidity < self.config["min_liquidity"]:
                continue

            # Calculate hours to expiry
            if market.end_date:
                hours_to_expiry = (market.end_date - current_time).total_seconds() / 3600
            else:
                hours_to_expiry = float('inf')

            selected.append({
                "market": market,
                "hours_to_expiry": hours_to_expiry,
                "liquidity": market.liquidity,
            })

        # Sort by priority: expiring soon + high liquidity
        selected.sort(key=lambda x: (
            x["hours_to_expiry"] < 24,  # Expiring within 24h first
            -x["liquidity"]              # Then by liquidity
        ), reverse=True)

        # Limit to max_markets
        selected = selected[:self.config["max_markets"]]

        market_ids = [s["market"].id for s in selected]

        return MarketSelection(
            markets=market_ids,
            priority_order=market_ids,  # Same as selection order
            execution_plan={
                "strategy": "time_decay_priority",
                "expiring_soon": [s["market"].id for s in selected if s["hours_to_expiry"] < 24],
            },
            metadata={
                "total_candidates": len(markets),
                "selected_count": len(market_ids),
            }
        )
# ==================== END EDITABLE ZONE ====================


# ==================== CONFIG ZONE - PARAMETERS ONLY ====================
DEFAULT_CONFIG = {
    "max_markets": 50,
    "min_liquidity": 1000,
    "categories": None,
}
# ==================== END CONFIG ZONE ====================
```

---

## 5. MCP Tools Specification

### 5.1 Polymarket Tools

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("get_price_history", "Get historical prices for a token", {
    "token_id": str,
    "interval": str,  # "1h" | "6h" | "1d" | "1w" | "max"
    "fidelity": int,  # Resolution in minutes (min: 1)
})
async def get_price_history(args: dict) -> dict:
    """Fetch price history from CLOB API."""
    # Implementation using existing clob.py
    pass

@tool("get_market_metadata", "Get market details", {
    "market_id": str,
})
async def get_market_metadata(args: dict) -> dict:
    """Fetch market metadata from Gamma API."""
    pass

@tool("get_orderbook", "Get current orderbook for a token", {
    "token_id": str,
})
async def get_orderbook(args: dict) -> dict:
    """Fetch current orderbook from CLOB API."""
    pass

@tool("get_negrisk_events", "Get NegRisk events with all outcomes", {
    "min_liquidity": float,
    "active_only": bool,
})
async def get_negrisk_events(args: dict) -> dict:
    """Fetch NegRisk events from Gamma API."""
    pass

polymarket_server = create_sdk_mcp_server(
    name="polymarket",
    version="1.0.0",
    tools=[get_price_history, get_market_metadata, get_orderbook, get_negrisk_events]
)
```

### 5.2 Paper Trading Tools

```python
@tool("run_forward_test", "Execute forward test with strategy", {
    "strategy_code": str,
    "template_name": str,
    "config": dict,
    "duration_hours": int,
    "initial_balance": float,
})
async def run_forward_test(args: dict) -> dict:
    """Run forward test using Paper Trading engine."""
    pass

@tool("get_performance_report", "Get performance metrics from test", {
    "session_id": str,
})
async def get_performance_report(args: dict) -> dict:
    """Get performance report from completed test."""
    pass

paper_trading_server = create_sdk_mcp_server(
    name="paper_trading",
    version="1.0.0",
    tools=[run_forward_test, get_performance_report]
)
```

### 5.3 Code Analysis Tools

```python
@tool("check_syntax", "Check Python syntax validity", {
    "code": str,
})
async def check_syntax(args: dict) -> dict:
    """Check if code has valid Python syntax."""
    pass

@tool("check_forbidden_ops", "Check for forbidden operations", {
    "code": str,
})
async def check_forbidden_ops(args: dict) -> dict:
    """AST analysis for forbidden operations."""
    forbidden = ["import", "exec", "eval", "open", "__"]
    # Implementation
    pass

@tool("validate_template", "Validate code against template rules", {
    "code": str,
    "template_name": str,
})
async def validate_template(args: dict) -> dict:
    """Validate FROZEN zone intact, correct return types, etc."""
    pass

code_analysis_server = create_sdk_mcp_server(
    name="code_analysis",
    version="1.0.0",
    tools=[check_syntax, check_forbidden_ops, validate_template]
)
```

---

## 6. Workflow Examples

### 6.1 Example 1: Order Imbalance Signal Strategy

```
User: "Order imbalance 기반 방향성 시그널 전략 개발해줘"

=== ORCHESTRATOR ===
Goal: {
    type: "signal",
    template: "SignalGenerator",
    hypothesis: "Order book imbalance > 30% predicts short-term price direction"
}

=== QUANT RESEARCHER ===
Output: {
    hypothesis: "Bid volume / total volume > 0.65 → price increase within 5 min",
    validation_method: "forward_test",
    test_duration_hours: 24,
    success_criteria: {
        "signal_accuracy": 0.55,
        "profitable_signals_pct": 0.52
    },
    preliminary_analysis: {
        "note": "Cannot backtest - no historical orderbook data"
    }
}

=== QUANT DEVELOPER ===
Modifies EDITABLE ZONE in SignalGenerator:
```python
def _calculate_signal(self, market_state, orderbook):
    bid_vol = sum(l.size for l in orderbook.bids[:5])
    ask_vol = sum(l.size for l in orderbook.asks[:5])

    if bid_vol + ask_vol < 1000:
        return Signal("NEUTRAL", 0.0, 0.3)

    ratio = bid_vol / (bid_vol + ask_vol)

    if ratio > 0.65:
        return Signal("LONG", ratio - 0.5, 0.7)
    elif ratio < 0.35:
        return Signal("SHORT", 0.5 - ratio, 0.7)
    return Signal("NEUTRAL", 0.0, 0.5)
```

=== SENIOR DEVELOPER ===
Review: {
    passed: true,
    issues: [],
    suggestions: ["Consider adding smoothing for noisy data"]
}

=== BACKTESTER ===
Forward test 24h results: {
    total_signals: 156,
    long_signals: 72,
    short_signals: 84,
    signal_accuracy: 0.58,
    profitable_signals_pct: 0.54
}

=== PORTFOLIO MANAGER ===
Decision: DEPLOY
Reasoning: "Accuracy 58% > target 55%, profit rate 54% > target 52%"
Deployment: {
    min_profit_filter: 0.02,
    alert_channels: ["discord", "telegram"]
}
```

### 6.2 Example 2: Composite Strategy (Signal + Arbitrage)

```
User: "NegRisk 아비트라지에 order imbalance 실행 타이밍 최적화 추가해줘"

=== ORCHESTRATOR ===
Goal: {
    type: "composite",
    templates: ["ArbitrageDetector", "SignalGenerator"],
    hypothesis: "Wait for favorable imbalance before executing arb legs"
}

=== Workflow proceeds with both templates ===
...
```

---

## 7. Safety & Security

### 7.1 Code Execution Sandbox

```python
FORBIDDEN_OPERATIONS = [
    "import",      # No new imports
    "exec",        # No dynamic execution
    "eval",        # No eval
    "open",        # No file access
    "requests",    # No HTTP
    "__",          # No dunder methods
    "subprocess",  # No shell
    "os.",         # No OS access
    "sys.",        # No sys access
]

def validate_code_safety(code: str) -> tuple[bool, List[str]]:
    """AST-based code safety validation."""
    import ast

    issues = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                issues.append(f"Forbidden: import statement")
            elif isinstance(node, ast.ImportFrom):
                issues.append(f"Forbidden: from import statement")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ["exec", "eval", "open", "compile"]:
                        issues.append(f"Forbidden: {node.func.id}()")
    except SyntaxError as e:
        issues.append(f"Syntax error: {e}")

    return len(issues) == 0, issues
```

### 7.2 Template Zone Enforcement

```python
async def enforce_zone_rules(
    input_data: HookInput,
    tool_use_id: str,
    context: HookContext
) -> HookJSONOutput:
    """PreToolUse hook to enforce zone rules."""

    if input_data["tool_name"] != "Edit":
        return {}

    old_string = input_data["tool_input"].get("old_string", "")
    file_path = input_data["tool_input"].get("file_path", "")

    # Check if editing a template file
    if "templates/" not in file_path:
        return {}

    # Deny if touching FROZEN ZONE markers
    if "FROZEN ZONE" in old_string or "END FROZEN ZONE" in old_string:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Cannot modify FROZEN ZONE markers"
            }
        }

    return {}
```

### 7.3 Resource Limits

```python
AGENT_LIMITS = {
    "orchestrator": {
        "max_turns": 50,
        "max_budget_usd": 10.0,
        "max_thinking_tokens": 20000,
    },
    "quant_researcher": {
        "max_turns": 20,
        "max_budget_usd": 3.0,
    },
    "quant_developer": {
        "max_turns": 30,
        "max_budget_usd": 5.0,
    },
    "senior_developer": {
        "max_turns": 10,
        "max_budget_usd": 1.0,
    },
    "backtester": {
        "max_turns": 15,
        "max_budget_usd": 2.0,
    },
    "portfolio_manager": {
        "max_turns": 10,
        "max_budget_usd": 1.0,
    },
}
```

---

## 8. Data Flow & Storage

### 8.1 Session Storage

```
data/
├── sessions/
│   └── {session_id}/
│       ├── goal.json           # Original goal
│       ├── plan.json           # Execution plan
│       ├── iterations/
│       │   └── {iteration_n}/
│       │       ├── hypothesis.json
│       │       ├── code.py
│       │       ├── review.json
│       │       ├── backtest_results.json
│       │       └── pm_decision.json
│       └── final_strategy/
│           ├── strategy.py
│           └── config.json
├── strategies/
│   └── deployed/
│       └── {strategy_id}/
│           ├── strategy.py
│           ├── config.json
│           └── performance_log.csv
└── templates/
    ├── signal_generator.py
    ├── arbitrage_detector.py
    └── market_selector.py
```

### 8.2 Performance Logging

```python
@dataclass
class PerformanceLog:
    timestamp: datetime
    strategy_id: str
    signal: Optional[Signal]
    opportunity: Optional[ArbitrageOpportunity]
    action_taken: str
    pnl: float
    metadata: dict
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

| Task | Priority | Estimated LOC |
|------|----------|---------------|
| Template base classes | P0 | 300 |
| Zone marker validation | P0 | 100 |
| MCP tools (polymarket) | P0 | 200 |
| Code safety checker | P0 | 150 |
| **Subtotal** | | **750** |

### Phase 2: Agents (Week 3-4)

| Task | Priority | Estimated LOC |
|------|----------|---------------|
| Orchestrator agent | P0 | 300 |
| Quant Researcher agent | P0 | 200 |
| Quant Developer agent | P0 | 200 |
| Senior Developer agent | P1 | 150 |
| Backtester agent | P0 | 200 |
| Portfolio Manager agent | P1 | 150 |
| **Subtotal** | | **1200** |

### Phase 3: Integration (Week 5-6)

| Task | Priority | Estimated LOC |
|------|----------|---------------|
| Agent workflow coordination | P0 | 300 |
| Forward testing integration | P0 | 200 |
| Session management | P1 | 150 |
| CLI interface | P2 | 100 |
| **Subtotal** | | **750** |

### Phase 4: Polish (Week 7-8)

| Task | Priority | Estimated LOC |
|------|----------|---------------|
| Error handling & logging | P1 | 200 |
| Performance optimization | P2 | 150 |
| Documentation | P1 | - |
| Testing | P0 | 400 |
| **Subtotal** | | **750** |

**Total Estimated LOC:** ~3,450

---

## 10. Success Metrics

### 10.1 System Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Strategy generation success rate | > 80% | Valid code produced / attempts |
| Code review pass rate | > 90% | Passed first review / total |
| Forward test completion rate | > 95% | Completed / started |
| Average iteration cycles | < 3 | Iterations to deploy or reject |

### 10.2 Strategy Performance Metrics

| Metric | Minimum | Target |
|--------|---------|--------|
| Signal accuracy | 52% | 60% |
| Arbitrage detection precision | 90% | 98% |
| Forward test Sharpe ratio | 0.5 | 1.5 |
| Max drawdown | < 15% | < 5% |

---

## 11. Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Agent generates unsafe code | Medium | High | AST validation + hooks |
| Forward test data insufficient | High | Medium | Minimum 24h test requirement |
| API rate limiting | Medium | Low | Caching + backoff |
| Strategy overfitting | Medium | High | Multiple market validation |
| Cost overrun | Low | Medium | Budget limits per agent |

---

## 12. Appendix

### A. Supported Strategies (v1.0)

| Strategy | Template | Complexity |
|----------|----------|------------|
| Order Imbalance | SignalGenerator | Low |
| Liquidity Vacuum | SignalGenerator | Medium |
| Sentiment Divergence | SignalGenerator | Medium |
| Whale Detection | SignalGenerator | Medium |
| Binary Underpriced | ArbitrageDetector | Low |
| Binary Overpriced | ArbitrageDetector | Low |
| NegRisk Underpriced | ArbitrageDetector | Medium |
| Cross-Event Correlation | ArbitrageDetector | High |
| Time Decay Filter | MarketSelector | Low |
| Volatility Regime | MarketSelector | Medium |
| Category Rotation | MarketSelector | Low |
| Multi-Leg Optimizer | MarketSelector | High |

### B. Claude Agent SDK Version Requirements

```
claude-agent-sdk >= 0.1.0
python >= 3.10
```

### C. Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional
POLYMARKET_WS_URL=wss://ws-subscriptions-clob.polymarket.com
POLYMARKET_CLOB_URL=https://clob.polymarket.com
POLYMARKET_GAMMA_URL=https://gamma-api.polymarket.com

# Alerts (optional)
DISCORD_WEBHOOK_URL=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

---

*Document Version: 1.0*
*Last Updated: 2025-01-05*
