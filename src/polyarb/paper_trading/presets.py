"""Preset trading modes for easy configuration"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any


class TradingMode(Enum):
    """Trading mode presets"""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


@dataclass
class ModeSettings:
    """Settings for a trading mode"""
    name: str
    min_profit: float  # Minimum profit %
    min_liquidity: float  # Minimum liquidity $
    position_size: float  # Position size $
    liquidity_cap_pct: float  # Max % of market liquidity to use
    # Simulation settings
    latency_ms: int  # Simulated execution latency
    failure_rate: float  # Probability of execution failure (0-1)
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "min_profit": self.min_profit,
            "min_liquidity": self.min_liquidity,
            "position_size": self.position_size,
            "liquidity_cap_pct": self.liquidity_cap_pct,
            "latency_ms": self.latency_ms,
            "failure_rate": self.failure_rate,
        }


# Preset configurations based on paper research
PRESETS: Dict[TradingMode, ModeSettings] = {
    TradingMode.CONSERVATIVE: ModeSettings(
        name="Conservative",
        min_profit=5.0,  # High margin for safety
        min_liquidity=10000,  # High liquidity only
        position_size=50,  # Small positions
        liquidity_cap_pct=1.0,  # Very low market impact
        latency_ms=3000,  # Pessimistic latency
        failure_rate=0.3,  # 30% of trades fail
        description="Safe mode: High margins, small positions, assumes worst-case execution",
    ),
    TradingMode.MODERATE: ModeSettings(
        name="Moderate",
        min_profit=3.0,  # Paper recommended
        min_liquidity=5000,
        position_size=100,
        liquidity_cap_pct=3.0,
        latency_ms=2000,
        failure_rate=0.2,  # 20% failure
        description="Balanced mode: Paper-recommended margins with realistic execution",
    ),
    TradingMode.AGGRESSIVE: ModeSettings(
        name="Aggressive",
        min_profit=1.0,  # Low threshold
        min_liquidity=1000,
        position_size=200,
        liquidity_cap_pct=5.0,
        latency_ms=1000,  # Optimistic
        failure_rate=0.1,  # 10% failure
        description="High-risk mode: Catches more opportunities but many will fail",
    ),
}


def get_preset(mode: TradingMode) -> ModeSettings:
    """Get settings for a preset mode"""
    return PRESETS[mode]


def get_mode_comparison() -> str:
    """Return a formatted comparison of all modes"""
    lines = [
        "Trading Mode Comparison:",
        "-" * 70,
        f"{'Mode':<15} {'Min Profit':<12} {'Position':<10} {'Latency':<10} {'Failure'}",
        "-" * 70,
    ]
    for mode, settings in PRESETS.items():
        lines.append(
            f"{settings.name:<15} {settings.min_profit:>5.1f}%       "
            f"${settings.position_size:<8.0f} {settings.latency_ms:>5}ms    "
            f"{settings.failure_rate*100:.0f}%"
        )
    lines.append("-" * 70)
    return "\n".join(lines)
