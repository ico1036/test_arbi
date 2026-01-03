# Polymarket Arbitrage Bot v3.4

## Quick Start

```bash
uv sync                                         # 설치
uv run python -m polyarb                        # 실시간 스캔
uv run python -m polyarb paper --mode moderate  # 페이퍼 트레이딩
uv run pytest                                   # 테스트 (94개)
```

## 페이퍼 트레이딩 결과

```bash
uv run python -m polyarb paper --mode moderate --duration 60
```

종료 시 자동 생성:
- `paper_trading_YYYYMMDD_HHMMSS.json` - 상세 데이터
- `paper_trading_YYYYMMDD_HHMMSS.png` - 시각화 차트

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

## 퀀트 전략 파라미터

수익률에 영향을 미치는 핵심 요소 3가지:

| 요소 | 설명 | 파라미터 | 구현 상태 |
|------|------|----------|-----------|
| **Selection** | 어떤 기회를 잡을지 | `--min-profit`, `--min-liquidity` | ✅ 구현됨 |
| **Sizing** | 얼마나 배팅할지 | `--size`, liquidity cap (5% 고정) | ⚠️ 부분 구현 |
| **Execution** | 실행 속도 (기계빨) | 미구현 | ❌ Phase 3 예정 |

### Selection (기회 선택)
```bash
# 보수적: 3% 이상, 유동성 $5,000 이상만
uv run python -m polyarb --min-profit 3 --min-liquidity 5000
```

### Sizing (배팅 크기)
```bash
# 기회당 $100 투자, 단 유동성의 5%까지만 (하드코딩)
uv run python -m polyarb paper --size 100
```
- `--size 100`: 기회당 최대 $100 투자
- 유동성 제한: 마켓 유동성의 5%까지만 사용 (슬리피지 방지)
- 예: 유동성 $1,000 마켓 → 최대 $50만 투자 가능

### Execution (실행) - 미구현
- 현재: Paper Trading만 지원 (즉시 체결 가정)
- Phase 3에서 `py-clob-client` 연동 예정

## CLI 옵션

### 주요 파라미터 설명

| 파라미터 | 의미 | 예시 |
|----------|------|------|
| `--min-profit 3` | 투자 대비 3% 이상 수익 기회만 감지 | $0.97 투자 → $1.00 수령 = 3.09% |
| `--min-liquidity 5000` | 유동성 $5,000 이상 마켓만 감지 | 유동성 낮으면 체결 어려움 |
| `--size 100` | 기회당 $100씩 투자 (페이퍼) | 유동성의 5%까지만 사용 |

**`--min-profit` 계산 방식:**
```
UNDERPRICED 예시:
  YES ask $0.48 + NO ask $0.49 = $0.97 투자
  시장 종료 시 $1.00 수령
  수익률 = ($1.00 - $0.97) / $0.97 = 3.09%

--min-profit 3 → 3% 이상만 감지 (이 기회는 감지됨)
--min-profit 5 → 5% 이상만 감지 (이 기회는 무시됨)
```

**권장 설정:**
- 낙관적: `--min-profit 1` (기회 많음, 실패 위험 높음)
- 보수적: `--min-profit 3` (실행 중 가격 변동 버퍼)
- 안전: `--min-profit 5` (기회 적음, 확실한 것만)

### 실시간 스캔 모드
| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--min-profit` | 1.0 | 최소 수익률 % (투자 대비) |
| `--min-liquidity` | 1000 | 최소 유동성 $ |
| `--max-markets` | 500 | 모니터링할 최대 마켓 수 |
| `--no-alerts` | - | 알림 비활성화 |
| `--no-log` | - | CSV 로깅 비활성화 |

### 페이퍼 트레이딩 모드

**프리셋 모드 (권장):**
```bash
uv run python -m polyarb paper --mode conservative  # 안전: 5%+, 실패율 30%
uv run python -m polyarb paper --mode moderate      # 균형: 3%+, 실패율 20%
uv run python -m polyarb paper --mode aggressive    # 공격: 1%+, 실패율 10%
```

| 모드 | Min Profit | Position Size | Failure Rate | 설명 |
|------|------------|---------------|--------------|------|
| conservative | 5% | $50 | 30% | 현실적 최악 시나리오 |
| moderate | 3% | $100 | 20% | 논문 권장 기준 |
| aggressive | 1% | $200 | 10% | 낙관적 시나리오 |

**커스텀 설정:**
```bash
uv run python -m polyarb paper --balance 10000 --size 100 --failure-rate 0.15
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--mode` | - | 프리셋 모드 (conservative/moderate/aggressive) |
| `--balance` | 10000 | 초기 가상 잔고 $ |
| `--size` | 100 | 기회당 투자 금액 $ |
| `--failure-rate` | 0 | 실행 실패율 시뮬레이션 (0-1) |
| `--latency` | 0 | 지연시간 시뮬레이션 (ms) |


## 알림 설정 (.env)

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=123456789
```

---

*v3.4 - PNG Summary Chart, 94 tests passing*
