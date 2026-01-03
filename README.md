# Polymarket Arbitrage Bot v3.0

## Quick Start (30초)

```bash
# 설치
uv sync

# 실행 (1회 스캔)
PYTHONPATH=src uv run python -m polyarb --once

# 연속 모니터링 (10초 간격)
PYTHONPATH=src uv run python -m polyarb --interval 10

# 테스트
PYTHONPATH=src uv run pytest
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
| `--interval` | 10 | 스캔 간격 (초) |
| `--once` | - | 1회만 스캔 |

## 알림 설정 (.env)

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=123456789
```

---

*v3.0 - 78 tests passing, Binary (underpriced + overpriced) & NegRisk detection*
