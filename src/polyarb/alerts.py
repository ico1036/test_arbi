"""
Alert system for notifications (Discord, Telegram)
"""
import aiohttp
from typing import Optional
from datetime import datetime

from .models import ArbitrageOpportunity
from .config import config


class AlertManager:
    """Async alert manager for multiple notification channels"""

    def __init__(self):
        self.discord_url = config.alerts.discord_webhook
        self.telegram_token = config.alerts.telegram_token
        self.telegram_chat_id = config.alerts.telegram_chat_id
        self.enabled = config.alerts.enabled
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send_discord(self, opp: ArbitrageOpportunity) -> bool:
        """Send alert to Discord webhook"""
        if not self.discord_url:
            return False

        # Build token details
        token_fields = []
        for i, token in enumerate(opp.tokens[:5]):  # Max 5 tokens in embed
            token_fields.append({
                "name": f"{token.outcome}",
                "value": f"${token.price:.4f}" if token.price else "N/A",
                "inline": True,
            })

        embed = {
            "title": f"🚨 {opp.arb_type.value.upper()} Opportunity!",
            "description": opp.question[:200],
            "color": 0x00FF00 if opp.profit_percent >= 3.0 else 0xFFFF00,
            "fields": [
                *token_fields,
                {"name": "Total Cost", "value": f"${opp.total_cost:.4f}", "inline": True},
                {"name": "💰 Profit", "value": f"${opp.profit:.4f} ({opp.profit_percent:.2f}%)", "inline": True},
                {"name": "💧 Liquidity", "value": f"${opp.liquidity:,.0f}", "inline": True},
                {"name": "Category", "value": opp.category or "Unknown", "inline": True},
            ],
            "url": opp.url,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Market Type: {opp.market_type.value}"},
        }

        try:
            async with self.session.post(
                self.discord_url,
                json={"embeds": [embed]},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                return response.status == 204
        except Exception as e:
            print(f"[Alert] Discord error: {e}")
            return False

    async def send_telegram(self, opp: ArbitrageOpportunity) -> bool:
        """Send alert to Telegram"""
        if not self.telegram_token or not self.telegram_chat_id:
            return False

        # Build token list
        token_lines = "\n".join(
            f"  {t.outcome}: ${t.price:.4f}" if t.price else f"  {t.outcome}: N/A"
            for t in opp.tokens[:8]
        )

        message = f"""🚨 *{opp.arb_type.value.upper()}*

📌 *Market:* {opp.question[:100]}...

*Prices:*
{token_lines}
━━━━━━━━━━━━━━
💰 *Profit:* ${opp.profit:.4f} (*{opp.profit_percent:.2f}%*)
💧 Liquidity: ${opp.liquidity:,.0f}
📊 Type: {opp.market_type.value}

🔗 [Open Market]({opp.url})
"""

        try:
            async with self.session.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                return response.status == 200
        except Exception as e:
            print(f"[Alert] Telegram error: {e}")
            return False

    async def send_all(self, opp: ArbitrageOpportunity):
        """Send alert to all configured channels"""
        if not self.enabled:
            return

        results = []
        if self.discord_url:
            results.append(await self.send_discord(opp))
        if self.telegram_token:
            results.append(await self.send_telegram(opp))

        return results

    async def send_summary(self, opportunities: list, scan_duration: float):
        """Send summary of scan results"""
        if not self.enabled or not opportunities:
            return

        summary = f"""📊 *Scan Summary*

Found {len(opportunities)} opportunities in {scan_duration:.1f}s

Top 3:
"""
        for i, opp in enumerate(opportunities[:3], 1):
            summary += f"{i}. {opp.profit_percent:.2f}% - {opp.question[:40]}...\n"

        if self.telegram_token and self.telegram_chat_id:
            try:
                await self.session.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json={
                        "chat_id": self.telegram_chat_id,
                        "text": summary,
                        "parse_mode": "Markdown",
                    },
                )
            except:
                pass
