"""
Summary Chart Generator - PNG output for paper trading results.

Simple matplotlib-based chart generation.
No external UI dependencies.
"""
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import PaperTradingEngine


class SummaryChart:
    """
    Generates PNG summary chart from PaperTradingEngine results.

    Usage:
        engine = PaperTradingEngine(...)
        # ... execute trades ...

        chart = SummaryChart(engine)
        chart.save("summary.png")
    """

    def __init__(self, engine: "PaperTradingEngine"):
        self.engine = engine
        self.metrics = engine.get_status()

    def save(self, filepath: str) -> str:
        """
        Save summary chart as PNG.

        Args:
            filepath: Output path (e.g., "summary.png")

        Returns:
            Saved file path
        """
        # Import matplotlib only when needed
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle(self._get_title(), fontsize=14, fontweight='bold')

        # 1. Key Metrics (top-left)
        self._draw_metrics_card(axes[0, 0])

        # 2. P&L Bar (top-right)
        self._draw_pnl_bar(axes[0, 1])

        # 3. Trade Stats (bottom-left)
        self._draw_trade_stats(axes[1, 0])

        # 4. Settings Info (bottom-right)
        self._draw_settings(axes[1, 1])

        plt.tight_layout()
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return filepath

    def _get_title(self) -> str:
        """Generate chart title"""
        mode = self.metrics.get("mode", "custom")
        runtime = self.metrics.get("runtime", "00:00:00")
        return f"Paper Trading Summary [{mode.upper()}] - Runtime: {runtime}"

    def _draw_metrics_card(self, ax):
        """Draw key metrics as text card"""
        ax.axis('off')

        metrics_text = [
            f"Initial Balance: ${self.metrics['initial_balance']:,.2f}",
            f"Final Balance:   ${self.metrics['balance']:,.2f}",
            "",
            f"Total P&L:       ${self.metrics['total_pnl']:+,.2f}",
            f"Return:          {self.metrics['return_percent']:+.2f}%",
            "",
            f"Win Rate:        {self.metrics['win_rate']*100:.1f}%",
            f"Max Drawdown:    {self.metrics['max_drawdown']:.1f}%",
        ]

        ax.text(0.1, 0.9, "KEY METRICS", fontsize=12, fontweight='bold',
                transform=ax.transAxes, verticalalignment='top')

        for i, line in enumerate(metrics_text):
            ax.text(0.1, 0.75 - i * 0.09, line, fontsize=10,
                    transform=ax.transAxes, fontfamily='monospace')

    def _draw_pnl_bar(self, ax):
        """Draw P&L bar chart"""
        pnl = self.metrics['total_pnl']
        ret = self.metrics['return_percent']

        color = '#2ecc71' if pnl >= 0 else '#e74c3c'

        ax.barh(['P&L'], [pnl], color=color, height=0.5)
        ax.axvline(x=0, color='black', linewidth=0.5)

        ax.set_title('Total P&L', fontsize=12, fontweight='bold')
        ax.set_xlabel('USD')

        # Add value label
        label_x = pnl + (abs(pnl) * 0.05) if pnl >= 0 else pnl - (abs(pnl) * 0.05)
        ax.text(label_x, 0, f"${pnl:+,.2f} ({ret:+.2f}%)",
                va='center', ha='left' if pnl >= 0 else 'right',
                fontweight='bold')

    def _draw_trade_stats(self, ax):
        """Draw trade statistics"""
        ax.axis('off')

        seen = self.metrics['opportunities_seen']
        executed = self.metrics['opportunities_executed']
        skipped = self.metrics['opportunities_skipped']
        failed = self.metrics['opportunities_failed']
        exec_rate = self.metrics['execution_rate']

        stats_text = [
            f"Opportunities Seen:     {seen}",
            f"Executed:               {executed}",
            f"Skipped:                {skipped}",
            f"Failed (simulation):    {failed}",
            "",
            f"Execution Rate:         {exec_rate:.1f}%",
        ]

        ax.text(0.1, 0.9, "TRADE STATISTICS", fontsize=12, fontweight='bold',
                transform=ax.transAxes, verticalalignment='top')

        for i, line in enumerate(stats_text):
            ax.text(0.1, 0.75 - i * 0.1, line, fontsize=10,
                    transform=ax.transAxes, fontfamily='monospace')

    def _draw_settings(self, ax):
        """Draw simulation settings"""
        ax.axis('off')

        mode = self.metrics.get('mode', 'custom')
        latency = self.metrics.get('latency_ms', 0)
        failure = self.metrics.get('failure_rate', 0)
        liq_cap = self.metrics.get('liquidity_cap_pct', 5.0)

        settings_text = [
            f"Mode:            {mode}",
            f"Latency:         {latency}ms",
            f"Failure Rate:    {failure*100:.0f}%",
            f"Liquidity Cap:   {liq_cap:.1f}%",
        ]

        ax.text(0.1, 0.9, "SIMULATION SETTINGS", fontsize=12, fontweight='bold',
                transform=ax.transAxes, verticalalignment='top')

        for i, line in enumerate(settings_text):
            ax.text(0.1, 0.75 - i * 0.12, line, fontsize=10,
                    transform=ax.transAxes, fontfamily='monospace')

        # Add mode description
        mode_desc = {
            'conservative': 'Safe: 5%+ profit, 30% failure',
            'moderate': 'Balanced: 3%+ profit, 20% failure',
            'aggressive': 'Risky: 1%+ profit, 10% failure',
            'custom': 'Custom settings',
        }
        desc = mode_desc.get(mode, '')
        ax.text(0.1, 0.25, desc, fontsize=9, style='italic',
                transform=ax.transAxes, color='gray')
