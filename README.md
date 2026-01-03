# Polymarket Arbitrage Bot v3.1

## Quick Start (30초)

```bash
uv sync                              # 설치
uv run python -m polyarb             # 실시간 스캔 (WebSocket)
uv run pytest                        # 테스트 (48개)
```

**출력 예시:**
```
⚡ Real-time WebSocket arbitrage detection

📊 Fetching markets...
   Found 264 binary markets
   Found 15 NegRisk events

✅ Registered:
   Binary markets: 187
   NegRisk events: 12
   Total tokens: 398

🔌 Connecting to WebSocket...
⚡ Listening for real-time price updates...

======================================================================
🎯 BINARY_UNDERPRICED [BUY] - 6.38% profit
======================================================================
📌 Will Bitcoin reach $100k by 2024?...
🔗 https://polymarket.com/event/will-btc-100k
----------------------------------------------------------------------
   YES ask: $0.4500
   NO ask:  $0.4800
   Total:   $0.9300
----------------------------------------------------------------------
💰 Profit: $0.0700 (6.38%)
💧 Liquidity: $45,230
💡 $2,261 → $144.24 profit
======================================================================
⏰ Detected at: 14:30:22.156
```

## 핵심 개념

**Binary Arbitrage**: YES + NO 가격 합이 $1이 아니면 차익 발생

| 상황 | 조건 | 전략 | 예시 |
|------|------|------|------|
| UNDERPRICED | ask합 < $1 | 둘 다 매수 → merge | $0.45 + $0.48 = $0.93 → 7% 수익 |
| OVERPRICED | bid합 > $1 | $1로 mint → 둘 다 매도 | $0.55 + $0.52 = $1.07 → 7% 수익 |

**NegRisk Arbitrage**: 다중 후보 마켓에서 모든 YES 합 < $1이면 차익 발생

```
A승 YES $0.20 + B승 YES $0.18 + C승 YES $0.17 + ... = $0.88 → 12% 수익
```

## CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--min-profit` | 1.0 | 최소 수익률 % |
| `--min-liquidity` | 1000 | 최소 유동성 $ |
| `--max-markets` | 500 | 모니터링할 최대 마켓 수 |
| `--no-alerts` | - | 알림 비활성화 |
| `--no-log` | - | CSV 로깅 비활성화 |

## 알림 설정 (.env)

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=123456789
```

---

*v3.1 - WebSocket 실시간 감지 (<100ms), 48 tests passing*
