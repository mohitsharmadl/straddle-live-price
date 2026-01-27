"""
Matplotlib chart generation for straddle price visualization.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import config


class ChartGenerator:
    """
    Generates line charts for straddle price tracking.

    Creates clean, auto-scaling charts with time on X-axis
    and straddle price on Y-axis.
    """

    def __init__(self, charts_dir: Optional[Path] = None):
        """
        Initialize chart generator.

        Args:
            charts_dir: Directory to save charts (default from config)
        """
        self.charts_dir = charts_dir or config.CHARTS_DIR
        self.charts_dir.mkdir(parents=True, exist_ok=True)

        # Style settings
        plt.style.use('seaborn-v0_8-whitegrid')

    def generate_chart(
        self,
        timestamps: list[datetime],
        straddle_prices: list[float],
        session_id: int,
        index_name: str,
        atm_strike: float,
        expiry_str: str,
        call_prices: Optional[list[float]] = None,
        put_prices: Optional[list[float]] = None,
        show_components: bool = False
    ) -> str:
        """
        Generate and save a straddle price chart.

        Args:
            timestamps: List of timestamps
            straddle_prices: List of straddle prices
            session_id: Database session ID
            index_name: Index name for title
            atm_strike: ATM strike price for title
            expiry_str: Expiry date string for title
            call_prices: Optional call prices for component view
            put_prices: Optional put prices for component view
            show_components: Whether to show CE/PE lines

        Returns:
            Path to saved chart file
        """
        if not timestamps or not straddle_prices:
            raise ValueError("No data to chart")

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 7))

        # Plot straddle line
        ax.plot(
            timestamps,
            straddle_prices,
            label='Straddle',
            color='#2E86AB',
            linewidth=2
        )

        # Optionally plot component prices
        if show_components and call_prices and put_prices:
            ax.plot(
                timestamps,
                call_prices,
                label='Call',
                color='#28A745',
                linewidth=1,
                linestyle='--',
                alpha=0.7
            )
            ax.plot(
                timestamps,
                put_prices,
                label='Put',
                color='#DC3545',
                linewidth=1,
                linestyle='--',
                alpha=0.7
            )

        # Format X-axis with time
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45)

        # Labels and title
        ax.set_xlabel('Time', fontsize=12)
        ax.set_ylabel('Price (₹)', fontsize=12)
        ax.set_title(
            f'{index_name} {int(atm_strike)} Straddle | Expiry: {expiry_str}',
            fontsize=14,
            fontweight='bold'
        )

        # Add current price annotation
        current_price = straddle_prices[-1]
        ax.annotate(
            f'₹{current_price:.2f}',
            xy=(timestamps[-1], current_price),
            xytext=(10, 0),
            textcoords='offset points',
            fontsize=11,
            fontweight='bold',
            color='#2E86AB'
        )

        # Calculate and show stats
        min_price = min(straddle_prices)
        max_price = max(straddle_prices)
        price_range = max_price - min_price

        stats_text = (
            f'High: ₹{max_price:.2f}\n'
            f'Low: ₹{min_price:.2f}\n'
            f'Range: ₹{price_range:.2f}'
        )
        ax.text(
            0.02, 0.98,
            stats_text,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8)
        )

        # Legend
        ax.legend(loc='upper right')

        # Grid styling
        ax.grid(True, alpha=0.3)

        # Tight layout
        plt.tight_layout()

        # Generate filename
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"straddle_{session_id}_{timestamp_str}.png"
        filepath = self.charts_dir / filename

        # Save
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)

        return str(filepath)

    def generate_live_chart(
        self,
        timestamps: list[datetime],
        straddle_prices: list[float],
        session_id: int,
        index_name: str,
        atm_strike: float,
        expiry_str: str
    ) -> str:
        """
        Generate a chart optimized for live updates.

        Uses a fixed filename so it can be refreshed.
        """
        if not timestamps or not straddle_prices:
            raise ValueError("No data to chart")

        fig, ax = plt.subplots(figsize=(12, 6))

        # Plot straddle line
        ax.plot(
            timestamps,
            straddle_prices,
            color='#2E86AB',
            linewidth=2
        )

        # Fill under curve
        ax.fill_between(
            timestamps,
            straddle_prices,
            alpha=0.1,
            color='#2E86AB'
        )

        # Format X-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)

        # Labels
        ax.set_xlabel('Time', fontsize=11)
        ax.set_ylabel('Straddle Price (₹)', fontsize=11)
        ax.set_title(
            f'{index_name} {int(atm_strike)} ATM Straddle - {expiry_str}',
            fontsize=13,
            fontweight='bold'
        )

        # Current price highlight
        current_price = straddle_prices[-1]
        ax.axhline(y=current_price, color='#E74C3C', linestyle=':', alpha=0.5)

        plt.tight_layout()

        # Save with fixed name for live updates
        filename = f"live_{session_id}.png"
        filepath = self.charts_dir / filename

        plt.savefig(filepath, dpi=100, bbox_inches='tight')
        plt.close(fig)

        return str(filepath)
