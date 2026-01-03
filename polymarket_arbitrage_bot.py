#!/usr/bin/env python3
"""
Polymarket Arbitrage Detection Bot
===================================
YES + NO 가격 합이 $1 미만일 때 차익거래 기회를 감지합니다.

작동 원리:
- YES 48¢ + NO 46¢ = 94¢ 지불
- 결과가 어떻게 나와도 $1 받음
- 순수익 = 6¢ (6.4% 수익률)

사용법:
    python polymarket_arbitrage_bot.py

주의: 이 봇은 기회 감지만 합니다. 실제 거래는 별도 설정 필요.
"""

import requests
import time
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

# API Endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Configuration
MIN_PROFIT_PERCENT = 1.0  # 최소 수익률 % (수수료 고려)
MIN_LIQUIDITY = 1000      # 최소 유동성 $
SCAN_INTERVAL = 5         # 스캔 간격 (초)
MAX_MARKETS = 500         # 최대 마켓 수


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
    timestamp: datetime


class PolymarketArbitrageBot:
    """Polymarket 차익거래 감지 봇"""
    
    def __init__(self, min_profit_percent: float = MIN_PROFIT_PERCENT,
                 min_liquidity: float = MIN_LIQUIDITY):
        self.min_profit_percent = min_profit_percent
        self.min_liquidity = min_liquidity
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PolymarketArbitrageBot/1.0',
            'Accept': 'application/json'
        })
        self.opportunities_found = 0
        
    def fetch_active_markets(self) -> List[Dict]:
        """활성 바이너리 마켓 목록 가져오기"""
        try:
            params = {
                'closed': 'false',
                'limit': MAX_MARKETS,
                'order': 'liquidityNum',
                'ascending': 'false'
            }
            response = self.session.get(f"{GAMMA_API}/markets", params=params)
            response.raise_for_status()
            markets = response.json()
            
            # 바이너리 마켓만 필터링 (YES/NO 형태)
            binary_markets = []
            for market in markets:
                # enableOrderBook이 true이고, clobTokenIds가 있는 마켓만
                if (market.get('enableOrderBook') and 
                    market.get('clobTokenIds') and
                    market.get('active') and
                    not market.get('closed')):
                    
                    # clobTokenIds 파싱 (JSON 문자열일 수 있음)
                    token_ids = market.get('clobTokenIds', '')
                    if isinstance(token_ids, str):
                        try:
                            token_ids = json.loads(token_ids)
                        except:
                            token_ids = token_ids.split(',') if ',' in token_ids else []
                    
                    # 정확히 2개의 토큰(YES/NO)이 있는 마켓
                    if len(token_ids) == 2:
                        market['parsed_token_ids'] = token_ids
                        binary_markets.append(market)
            
            return binary_markets
            
        except Exception as e:
            print(f"❌ 마켓 목록 가져오기 실패: {e}")
            return []
    
    def get_order_book_prices(self, token_id: str) -> Tuple[Optional[float], Optional[float]]:
        """오더북에서 best bid/ask 가격 가져오기"""
        try:
            response = self.session.get(f"{CLOB_API}/book", params={'token_id': token_id})
            response.raise_for_status()
            book = response.json()
            
            # Best bid (매수 최고가) - 우리가 팔 수 있는 가격
            bids = book.get('bids', [])
            best_bid = float(bids[0]['price']) if bids else None
            
            # Best ask (매도 최저가) - 우리가 살 수 있는 가격
            asks = book.get('asks', [])
            best_ask = float(asks[0]['price']) if asks else None
            
            return best_bid, best_ask
            
        except Exception as e:
            return None, None
    
    def get_midpoint_price(self, token_id: str) -> Optional[float]:
        """토큰의 중간 가격 가져오기"""
        try:
            response = self.session.get(f"{CLOB_API}/midpoint", params={'token_id': token_id})
            response.raise_for_status()
            data = response.json()
            return float(data.get('mid', 0))
        except:
            return None
    
    def get_best_ask_price(self, token_id: str) -> Optional[float]:
        """토큰의 best ask (매도 최저가) 가져오기 - 즉시 구매 가능 가격"""
        try:
            response = self.session.get(
                f"{CLOB_API}/price",
                params={'token_id': token_id, 'side': 'buy'}
            )
            response.raise_for_status()
            data = response.json()
            return float(data.get('price', 0))
        except:
            return None

    def check_arbitrage(self, market: Dict) -> Optional[ArbitrageOpportunity]:
        """마켓에서 차익거래 기회 확인"""
        token_ids = market.get('parsed_token_ids', [])
        if len(token_ids) != 2:
            return None
        
        yes_token_id = token_ids[0]
        no_token_id = token_ids[1]
        
        # Best ask 가격 가져오기 (즉시 구매 가능한 가격)
        yes_ask = self.get_best_ask_price(yes_token_id)
        no_ask = self.get_best_ask_price(no_token_id)
        
        if yes_ask is None or no_ask is None:
            return None
        
        if yes_ask <= 0 or no_ask <= 0:
            return None
        
        # 총 비용 계산
        total_cost = yes_ask + no_ask
        
        # 차익 계산 ($1 - 총비용)
        profit = 1.0 - total_cost
        profit_percent = (profit / total_cost) * 100 if total_cost > 0 else 0
        
        # 수익률이 최소 기준 이상인 경우만
        if profit_percent >= self.min_profit_percent:
            liquidity = market.get('liquidityNum', 0) or 0
            
            # 유동성 체크
            if liquidity < self.min_liquidity:
                return None
            
            slug = market.get('slug', '')
            return ArbitrageOpportunity(
                market_id=market.get('id', ''),
                question=market.get('question', 'Unknown'),
                slug=slug,
                yes_price=yes_ask,
                no_price=no_ask,
                total_cost=total_cost,
                profit=profit,
                profit_percent=profit_percent,
                liquidity=liquidity,
                url=f"https://polymarket.com/event/{slug}" if slug else "",
                timestamp=datetime.now()
            )
        
        return None
    
    def scan_all_markets(self) -> List[ArbitrageOpportunity]:
        """모든 마켓 스캔하여 차익거래 기회 찾기"""
        opportunities = []
        
        print(f"\n🔍 마켓 스캔 중... ({datetime.now().strftime('%H:%M:%S')})")
        markets = self.fetch_active_markets()
        print(f"   📊 {len(markets)}개 바이너리 마켓 발견")
        
        for i, market in enumerate(markets):
            # 진행 상황 표시 (50개마다)
            if (i + 1) % 50 == 0:
                print(f"   ⏳ {i + 1}/{len(markets)} 마켓 분석 중...")
            
            opportunity = self.check_arbitrage(market)
            if opportunity:
                opportunities.append(opportunity)
                self.opportunities_found += 1
            
            # API 레이트 리밋 방지
            time.sleep(0.05)
        
        return opportunities
    
    def display_opportunity(self, opp: ArbitrageOpportunity):
        """차익거래 기회 표시"""
        print("\n" + "="*70)
        print("🚨 차익거래 기회 발견!")
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
        print(f"   ⏰ 발견 시간: {opp.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        # 예상 수익 계산
        investment = min(1000, opp.liquidity * 0.1)  # 유동성의 10% 또는 $1000
        expected_profit = investment * (opp.profit_percent / 100)
        print(f"\n   💡 ${investment:,.0f} 투자 시 예상 수익: ${expected_profit:.2f}")
    
    def run_once(self) -> List[ArbitrageOpportunity]:
        """한 번 스캔 실행"""
        opportunities = self.scan_all_markets()
        
        if opportunities:
            # 수익률 높은 순으로 정렬
            opportunities.sort(key=lambda x: x.profit_percent, reverse=True)
            
            for opp in opportunities:
                self.display_opportunity(opp)
        else:
            print("   ❌ 현재 차익거래 기회 없음")
        
        return opportunities
    
    def run_continuous(self, interval: int = SCAN_INTERVAL):
        """연속 모니터링 실행"""
        print("="*70)
        print("🤖 Polymarket 차익거래 봇 시작")
        print("="*70)
        print(f"   최소 수익률: {self.min_profit_percent}%")
        print(f"   최소 유동성: ${self.min_liquidity:,}")
        print(f"   스캔 간격: {interval}초")
        print("="*70)
        print("\n⚡ 모니터링 시작... (Ctrl+C로 중지)")
        
        try:
            while True:
                self.run_once()
                print(f"\n⏳ {interval}초 후 다시 스캔...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 봇 종료")
            print(f"📊 총 발견한 기회: {self.opportunities_found}개")


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Polymarket 차익거래 감지 봇')
    parser.add_argument('--min-profit', type=float, default=MIN_PROFIT_PERCENT,
                        help=f'최소 수익률 %% (기본: {MIN_PROFIT_PERCENT})')
    parser.add_argument('--min-liquidity', type=float, default=MIN_LIQUIDITY,
                        help=f'최소 유동성 $ (기본: {MIN_LIQUIDITY})')
    parser.add_argument('--interval', type=int, default=SCAN_INTERVAL,
                        help=f'스캔 간격 초 (기본: {SCAN_INTERVAL})')
    parser.add_argument('--once', action='store_true',
                        help='한 번만 스캔 후 종료')
    
    args = parser.parse_args()
    
    bot = PolymarketArbitrageBot(
        min_profit_percent=args.min_profit,
        min_liquidity=args.min_liquidity
    )
    
    if args.once:
        bot.run_once()
    else:
        bot.run_continuous(interval=args.interval)


if __name__ == "__main__":
    main()
