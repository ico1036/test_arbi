#!/usr/bin/env python3
"""
Polymarket Arbitrage Detection Bot v2.0
========================================
YES + NO 가격 합이 $1 미만일 때 차익거래 기회를 감지합니다.

기능:
- 실시간 마켓 모니터링
- Discord/Telegram 알림 (선택)
- 수익률/유동성 필터링
- 히스토리 로깅

설치:
    pip install requests python-dotenv

설정:
    .env 파일 생성 후 아래 내용 추가 (선택사항):
    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
    TELEGRAM_BOT_TOKEN=your_bot_token
    TELEGRAM_CHAT_ID=your_chat_id

사용법:
    python polymarket_arbitrage_bot_v2.py
    python polymarket_arbitrage_bot_v2.py --min-profit 2 --min-liquidity 5000
    python polymarket_arbitrage_bot_v2.py --once
"""

import requests
import time
import json
import os
import csv
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

# .env 파일 로드 시도
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# API Endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Configuration
MIN_PROFIT_PERCENT = 1.0      # 최소 수익률 % (수수료 약 0.5% 고려)
MIN_LIQUIDITY = 1000          # 최소 유동성 $
SCAN_INTERVAL = 10            # 스캔 간격 (초)
MAX_MARKETS = 500             # 최대 마켓 수
LOG_FILE = "arbitrage_opportunities.csv"

# Alert Configuration (환경변수에서 읽음)
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


@dataclass
class ArbitrageOpportunity:
    """차익거래 기회 정보"""
    market_id: str
    question: str
    slug: str
    yes_price: float
    no_price: float
    total_cost: float
    profit: float
    profit_percent: float
    liquidity: float
    url: str
    timestamp: str
    yes_token_id: str = ""
    no_token_id: str = ""


class AlertManager:
    """알림 관리자"""
    
    @staticmethod
    def send_discord(opp: ArbitrageOpportunity) -> bool:
        """Discord 웹훅으로 알림 전송"""
        if not DISCORD_WEBHOOK_URL:
            return False
        
        try:
            embed = {
                "title": "🚨 차익거래 기회 발견!",
                "description": opp.question[:200],
                "color": 0x00ff00,
                "fields": [
                    {"name": "YES 가격", "value": f"${opp.yes_price:.4f}", "inline": True},
                    {"name": "NO 가격", "value": f"${opp.no_price:.4f}", "inline": True},
                    {"name": "총 비용", "value": f"${opp.total_cost:.4f}", "inline": True},
                    {"name": "💰 수익", "value": f"${opp.profit:.4f} ({opp.profit_percent:.2f}%)", "inline": True},
                    {"name": "💧 유동성", "value": f"${opp.liquidity:,.0f}", "inline": True},
                ],
                "url": opp.url,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"embeds": [embed]},
                timeout=10
            )
            return response.status_code == 204
        except Exception as e:
            print(f"Discord 알림 실패: {e}")
            return False
    
    @staticmethod
    def send_telegram(opp: ArbitrageOpportunity) -> bool:
        """Telegram으로 알림 전송"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return False
        
        try:
            message = f"""🚨 *차익거래 기회 발견!*

📌 *마켓:* {opp.question[:100]}...

💵 YES: ${opp.yes_price:.4f}
💵 NO: ${opp.no_price:.4f}
━━━━━━━━━━━━━━
💰 *수익:* ${opp.profit:.4f} (*{opp.profit_percent:.2f}%*)
💧 유동성: ${opp.liquidity:,.0f}

🔗 [마켓 열기]({opp.url})
"""
            
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram 알림 실패: {e}")
            return False
    
    @staticmethod
    def send_all(opp: ArbitrageOpportunity):
        """모든 설정된 채널로 알림 전송"""
        AlertManager.send_discord(opp)
        AlertManager.send_telegram(opp)


class PolymarketArbitrageBot:
    """Polymarket 차익거래 감지 봇"""
    
    def __init__(self, min_profit_percent: float = MIN_PROFIT_PERCENT,
                 min_liquidity: float = MIN_LIQUIDITY,
                 enable_alerts: bool = True,
                 enable_logging: bool = True):
        self.min_profit_percent = min_profit_percent
        self.min_liquidity = min_liquidity
        self.enable_alerts = enable_alerts
        self.enable_logging = enable_logging
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PolymarketArbitrageBot/2.0',
            'Accept': 'application/json'
        })
        
        self.opportunities_found = 0
        self.seen_opportunities = set()  # 중복 알림 방지
        
        # 로그 파일 초기화
        if enable_logging and not Path(LOG_FILE).exists():
            self._init_log_file()
    
    def _init_log_file(self):
        """CSV 로그 파일 초기화"""
        with open(LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'market_id', 'question', 'yes_price', 'no_price',
                'total_cost', 'profit', 'profit_percent', 'liquidity', 'url'
            ])
    
    def _log_opportunity(self, opp: ArbitrageOpportunity):
        """기회를 CSV에 기록"""
        if not self.enable_logging:
            return
        
        with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                opp.timestamp, opp.market_id, opp.question[:100],
                opp.yes_price, opp.no_price, opp.total_cost,
                opp.profit, opp.profit_percent, opp.liquidity, opp.url
            ])
    
    def fetch_active_markets(self) -> List[Dict]:
        """활성 바이너리 마켓 목록 가져오기"""
        try:
            params = {
                'closed': 'false',
                'limit': MAX_MARKETS,
                'order': 'liquidityNum',
                'ascending': 'false'
            }
            response = self.session.get(
                f"{GAMMA_API}/markets",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            markets = response.json()
            
            # 바이너리 마켓만 필터링
            binary_markets = []
            for market in markets:
                if not market.get('enableOrderBook'):
                    continue
                if not market.get('clobTokenIds'):
                    continue
                if not market.get('active') or market.get('closed'):
                    continue
                
                # clobTokenIds 파싱
                token_ids = market.get('clobTokenIds', '')
                if isinstance(token_ids, str):
                    try:
                        token_ids = json.loads(token_ids)
                    except:
                        token_ids = [t.strip() for t in token_ids.split(',') if t.strip()]
                
                # 정확히 2개의 토큰(YES/NO)이 있는 마켓
                if len(token_ids) == 2:
                    market['parsed_token_ids'] = token_ids
                    binary_markets.append(market)
            
            return binary_markets
            
        except requests.exceptions.RequestException as e:
            print(f"❌ 마켓 목록 가져오기 실패: {e}")
            return []
    
    def get_best_ask_price(self, token_id: str) -> Optional[float]:
        """토큰의 best ask (매도 최저가) 가져오기"""
        try:
            response = self.session.get(
                f"{CLOB_API}/price",
                params={'token_id': token_id, 'side': 'buy'},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            price = data.get('price')
            return float(price) if price else None
        except:
            return None
    
    def get_order_book(self, token_id: str) -> Dict:
        """오더북 전체 가져오기"""
        try:
            response = self.session.get(
                f"{CLOB_API}/book",
                params={'token_id': token_id},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except:
            return {}

    def check_arbitrage(self, market: Dict) -> Optional[ArbitrageOpportunity]:
        """마켓에서 차익거래 기회 확인"""
        token_ids = market.get('parsed_token_ids', [])
        if len(token_ids) != 2:
            return None
        
        yes_token_id = token_ids[0]
        no_token_id = token_ids[1]
        
        # Best ask 가격 가져오기
        yes_ask = self.get_best_ask_price(yes_token_id)
        no_ask = self.get_best_ask_price(no_token_id)
        
        if yes_ask is None or no_ask is None:
            return None
        
        if yes_ask <= 0 or no_ask <= 0:
            return None
        
        # 총 비용 및 차익 계산
        total_cost = yes_ask + no_ask
        profit = 1.0 - total_cost
        profit_percent = (profit / total_cost) * 100 if total_cost > 0 else 0
        
        # 수익률 체크
        if profit_percent < self.min_profit_percent:
            return None
        
        # 유동성 체크
        liquidity = market.get('liquidityNum', 0) or 0
        if liquidity < self.min_liquidity:
            return None
        
        slug = market.get('slug', '')
        
        return ArbitrageOpportunity(
            market_id=str(market.get('id', '')),
            question=market.get('question', 'Unknown'),
            slug=slug,
            yes_price=yes_ask,
            no_price=no_ask,
            total_cost=total_cost,
            profit=profit,
            profit_percent=profit_percent,
            liquidity=liquidity,
            url=f"https://polymarket.com/event/{slug}" if slug else "",
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            yes_token_id=yes_token_id,
            no_token_id=no_token_id
        )
    
    def scan_all_markets(self) -> List[ArbitrageOpportunity]:
        """모든 마켓 스캔"""
        opportunities = []
        
        print(f"\n🔍 마켓 스캔 중... ({datetime.now().strftime('%H:%M:%S')})")
        markets = self.fetch_active_markets()
        
        if not markets:
            print("   ⚠️ 마켓을 가져올 수 없습니다.")
            return []
        
        print(f"   📊 {len(markets)}개 바이너리 마켓 발견")
        
        for i, market in enumerate(markets):
            if (i + 1) % 50 == 0:
                print(f"   ⏳ {i + 1}/{len(markets)} 마켓 분석 중...")
            
            opportunity = self.check_arbitrage(market)
            if opportunity:
                opportunities.append(opportunity)
                self.opportunities_found += 1
            
            time.sleep(0.05)  # Rate limit 방지
        
        return opportunities
    
    def display_opportunity(self, opp: ArbitrageOpportunity, is_new: bool = True):
        """차익거래 기회 표시"""
        status = "🆕 NEW" if is_new else "📍 ACTIVE"
        
        print("\n" + "="*70)
        print(f"🚨 차익거래 기회 {status}")
        print("="*70)
        print(f"📌 마켓: {opp.question[:60]}...")
        print(f"🔗 URL: {opp.url}")
        print("-"*70)
        print(f"   YES 가격: ${opp.yes_price:.4f}")
        print(f"   NO 가격:  ${opp.no_price:.4f}")
        print(f"   ─────────────────────")
        print(f"   총 비용:  ${opp.total_cost:.4f}")
        print(f"   정산금:   $1.0000")
        print(f"   ─────────────────────")
        print(f"   💰 순수익: ${opp.profit:.4f} ({opp.profit_percent:.2f}%)")
        print(f"   💧 유동성: ${opp.liquidity:,.0f}")
        print("="*70)
        
        # 투자 시뮬레이션
        for investment in [100, 500, 1000, 5000]:
            if investment <= opp.liquidity * 0.1:
                expected = investment * (opp.profit_percent / 100)
                print(f"   💡 ${investment:,} 투자 → ${expected:.2f} 수익")
    
    def run_once(self) -> List[ArbitrageOpportunity]:
        """한 번 스캔 실행"""
        opportunities = self.scan_all_markets()
        
        if opportunities:
            opportunities.sort(key=lambda x: x.profit_percent, reverse=True)
            
            for opp in opportunities:
                opp_key = f"{opp.market_id}_{opp.profit_percent:.2f}"
                is_new = opp_key not in self.seen_opportunities
                
                self.display_opportunity(opp, is_new)
                
                if is_new:
                    self.seen_opportunities.add(opp_key)
                    self._log_opportunity(opp)
                    
                    if self.enable_alerts:
                        AlertManager.send_all(opp)
        else:
            print("   ❌ 현재 차익거래 기회 없음")
        
        return opportunities
    
    def run_continuous(self, interval: int = SCAN_INTERVAL):
        """연속 모니터링"""
        self._print_banner()
        
        try:
            while True:
                self.run_once()
                print(f"\n⏳ {interval}초 후 다시 스캔...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 봇 종료")
            print(f"📊 총 발견한 기회: {self.opportunities_found}개")
            if self.enable_logging:
                print(f"📁 로그 파일: {LOG_FILE}")
    
    def _print_banner(self):
        """배너 출력"""
        alerts = []
        if DISCORD_WEBHOOK_URL:
            alerts.append("Discord")
        if TELEGRAM_BOT_TOKEN:
            alerts.append("Telegram")
        
        print("="*70)
        print("🤖 Polymarket 차익거래 봇 v2.0")
        print("="*70)
        print(f"   최소 수익률: {self.min_profit_percent}%")
        print(f"   최소 유동성: ${self.min_liquidity:,}")
        print(f"   알림: {', '.join(alerts) if alerts else '없음 (.env 설정 필요)'}")
        print(f"   로깅: {'활성화' if self.enable_logging else '비활성화'}")
        print("="*70)
        print("\n⚡ 모니터링 시작... (Ctrl+C로 중지)")


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Polymarket 차익거래 감지 봇',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    python polymarket_arbitrage_bot_v2.py                    # 기본 설정으로 실행
    python polymarket_arbitrage_bot_v2.py --once             # 한 번만 스캔
    python polymarket_arbitrage_bot_v2.py --min-profit 2     # 2% 이상만
    python polymarket_arbitrage_bot_v2.py --min-liquidity 10000  # 유동성 $10k 이상만
        """
    )
    parser.add_argument('--min-profit', type=float, default=MIN_PROFIT_PERCENT,
                        help=f'최소 수익률 %% (기본: {MIN_PROFIT_PERCENT})')
    parser.add_argument('--min-liquidity', type=float, default=MIN_LIQUIDITY,
                        help=f'최소 유동성 $ (기본: {MIN_LIQUIDITY})')
    parser.add_argument('--interval', type=int, default=SCAN_INTERVAL,
                        help=f'스캔 간격 초 (기본: {SCAN_INTERVAL})')
    parser.add_argument('--once', action='store_true',
                        help='한 번만 스캔 후 종료')
    parser.add_argument('--no-alerts', action='store_true',
                        help='알림 비활성화')
    parser.add_argument('--no-log', action='store_true',
                        help='로깅 비활성화')
    
    args = parser.parse_args()
    
    bot = PolymarketArbitrageBot(
        min_profit_percent=args.min_profit,
        min_liquidity=args.min_liquidity,
        enable_alerts=not args.no_alerts,
        enable_logging=not args.no_log
    )
    
    if args.once:
        bot.run_once()
    else:
        bot.run_continuous(interval=args.interval)


if __name__ == "__main__":
    main()
