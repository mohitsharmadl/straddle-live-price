#!/usr/bin/env python3
"""
Straddle Live Price Tracker

A CLI application that tracks ATM straddle prices for NIFTY/SENSEX options
in real-time using Zerodha Kite API.

Usage:
    python main.py

The application will:
1. Authenticate with Zerodha Kite (opens browser for login if needed)
2. Let you select an index (NIFTY/SENSEX) and expiry date
3. Calculate the ATM strike and start tracking straddle prices
4. Store every tick in PostgreSQL
5. Generate charts at configured intervals
"""
import asyncio
import sys
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

from config import config
from kite_client import KiteClient
from straddle_calculator import StraddleCalculator, StraddlePrice
from scheduler import StraddleTracker, MarketScheduler
from db import init_db


console = Console()


def print_header():
    """Print application header."""
    console.print(Panel.fit(
        "[bold blue]Straddle Live Price Tracker[/bold blue]\n"
        "[dim]Track ATM straddle prices in real-time[/dim]",
        border_style="blue"
    ))


def validate_config() -> bool:
    """Validate required configuration."""
    missing = config.validate()
    if missing:
        console.print(
            f"[red]Missing configuration: {', '.join(missing)}[/red]\n"
            "Please set these in your .env file."
        )
        return False
    return True


def select_index() -> str:
    """Interactive index selection."""
    console.print("\n[bold]Select Index:[/bold]")
    console.print("  1. NIFTY")
    console.print("  2. SENSEX")

    choice = IntPrompt.ask("Enter choice", choices=["1", "2"], default="1")
    return "NIFTY" if choice == 1 else "SENSEX"


def select_expiry(kite_client: KiteClient, index_name: str):
    """Interactive expiry selection."""
    console.print("\n[dim]Fetching available expiries...[/dim]")

    expiries = kite_client.get_expiries(index_name)

    if not expiries:
        console.print("[red]No expiries found![/red]")
        return None

    # Show only next 5 expiries
    display_expiries = expiries[:5]

    console.print("\n[bold]Available Expiries:[/bold]")
    for i, exp in enumerate(display_expiries, 1):
        console.print(f"  {i}. {exp.strftime('%d-%b-%Y')}")

    choice = IntPrompt.ask(
        "Enter choice",
        default=1
    )

    if 1 <= choice <= len(display_expiries):
        return display_expiries[choice - 1]

    console.print("[red]Invalid choice[/red]")
    return None


def create_tick_callback(console: Console):
    """Create a callback function for displaying ticks."""
    tick_count = [0]  # Mutable container for closure

    def on_tick(price: StraddlePrice, timestamp: datetime):
        tick_count[0] += 1
        time_str = timestamp.strftime('%H:%M:%S')

        # Color based on price movement (would need previous price for real comparison)
        price_str = f"₹{price.straddle_price:.2f}"

        console.print(
            f"[dim][{time_str}][/dim] "
            f"Straddle: [bold cyan]{price_str}[/bold cyan]  "
            f"[dim](CE: ₹{price.call_price:.2f} | PE: ₹{price.put_price:.2f})[/dim]"
        )

    return on_tick


async def run_tracker(
    kite_client: KiteClient,
    index_name: str,
    expiry
):
    """Run the straddle tracker."""
    calculator = StraddleCalculator(kite_client)

    # Get straddle info
    console.print("\n[dim]Calculating ATM strike...[/dim]")
    straddle_info = calculator.get_straddle_info(index_name, expiry)

    # Display straddle configuration
    table = Table(title="Straddle Configuration", show_header=False)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Index", straddle_info.index_name)
    table.add_row("Expiry", straddle_info.expiry.strftime('%d-%b-%Y'))
    table.add_row("Spot Price", f"₹{straddle_info.spot_price:.2f}")
    table.add_row("ATM Strike", f"{int(straddle_info.atm_strike)}")
    table.add_row("Call Symbol", straddle_info.call_symbol)
    table.add_row("Put Symbol", straddle_info.put_symbol)

    console.print(table)

    # Confirm start
    console.print("\n[dim]Press Enter to start tracking (Ctrl+C to stop)[/dim]")
    input()

    # Create tracker
    tick_callback = create_tick_callback(console)
    tracker = StraddleTracker(
        kite_client=kite_client,
        straddle_info=straddle_info,
        on_tick=tick_callback
    )

    # Create scheduler and run
    scheduler = MarketScheduler(tracker)

    console.print("\n[bold green]Starting live tracking...[/bold green]\n")

    try:
        await scheduler.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        scheduler.shutdown()

    # Print summary
    console.print(f"\n[bold]Session Summary[/bold]")
    console.print(f"  Ticks recorded: {tracker.tick_count}")
    console.print(f"  Session ID: {tracker.session_id}")


def main():
    """Main entry point."""
    print_header()

    # Validate configuration
    if not validate_config():
        sys.exit(1)

    # Initialize database
    console.print("[dim]Initializing database...[/dim]")
    try:
        init_db()
    except Exception as e:
        console.print(f"[red]Database error: {e}[/red]")
        console.print("[dim]Make sure PostgreSQL is running and DATABASE_URL is correct[/dim]")
        sys.exit(1)

    # Initialize Kite client
    kite_client = KiteClient()

    # Authenticate
    console.print("\n[bold]Authenticating with Zerodha Kite...[/bold]")
    if not kite_client.authenticate():
        console.print("[red]Authentication failed![/red]")
        sys.exit(1)

    try:
        profile = kite_client.get_profile()
        console.print(f"[green]Logged in as: {profile['user_name']}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to get profile: {e}[/red]")
        sys.exit(1)

    # Select index
    index_name = select_index()

    # Select expiry
    expiry = select_expiry(kite_client, index_name)
    if not expiry:
        sys.exit(1)

    # Run tracker
    try:
        asyncio.run(run_tracker(kite_client, index_name, expiry))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    console.print("\n[bold green]Done![/bold green]")


if __name__ == '__main__':
    main()
