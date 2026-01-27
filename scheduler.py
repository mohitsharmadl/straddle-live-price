"""
Scheduler for 1-second price tracking during market hours.
"""
import asyncio
import signal
from datetime import datetime, time
from decimal import Decimal
from typing import Callable, Optional
import threading

from config import config
from kite_client import KiteClient
from straddle_calculator import StraddleCalculator, StraddleInfo, StraddlePrice
from db import get_session, StraddleRepository
from chart import ChartGenerator


class StraddleTracker:
    """
    Real-time straddle price tracker.

    Fetches prices every second via WebSocket, stores in database,
    and generates periodic charts.
    """

    def __init__(
        self,
        kite_client: KiteClient,
        straddle_info: StraddleInfo,
        on_tick: Optional[Callable[[StraddlePrice, datetime], None]] = None
    ):
        """
        Initialize tracker.

        Args:
            kite_client: Authenticated Kite client
            straddle_info: Straddle configuration
            on_tick: Optional callback for each price tick
        """
        self.kite = kite_client
        self.straddle = straddle_info
        self.on_tick = on_tick

        self.calculator = StraddleCalculator(kite_client)
        self.chart_gen = ChartGenerator()

        self._running = False
        self._session_id: Optional[int] = None
        self._last_chart_time: Optional[datetime] = None
        self._tick_count = 0

        # Price caches (updated by WebSocket)
        self._call_price: Optional[float] = None
        self._put_price: Optional[float] = None
        self._last_update: Optional[datetime] = None

        # Data for charting
        self._timestamps: list[datetime] = []
        self._straddle_prices: list[float] = []

    def _is_market_open(self) -> bool:
        """Check if we're within market hours."""
        now = datetime.now().time()
        market_open = time(
            config.MARKET_OPEN_HOUR,
            config.MARKET_OPEN_MINUTE
        )
        market_close = time(
            config.MARKET_CLOSE_HOUR,
            config.MARKET_CLOSE_MINUTE
        )
        return market_open <= now <= market_close

    def _on_price_update(self, tick: dict):
        """Handle WebSocket price update."""
        token = tick['instrument_token']
        price = tick['last_price']

        if token == self.straddle.call_token:
            self._call_price = price
        elif token == self.straddle.put_token:
            self._put_price = price

        self._last_update = datetime.now()

    def _start_websocket(self):
        """Start WebSocket streaming for option prices."""
        tokens = [
            self.straddle.call_token,
            self.straddle.put_token
        ]
        self.kite.start_ticker(tokens, self._on_price_update)

    def _save_tick(self, repo: StraddleRepository, straddle_price: StraddlePrice):
        """Save tick to database."""
        if self._session_id:
            repo.add_tick(
                session_id=self._session_id,
                call_price=Decimal(str(straddle_price.call_price)),
                put_price=Decimal(str(straddle_price.put_price)),
                spot_price=Decimal(str(straddle_price.spot_price)) if straddle_price.spot_price else None
            )

    def _maybe_generate_chart(self, repo: StraddleRepository) -> Optional[str]:
        """Generate chart if interval has passed."""
        now = datetime.now()

        if self._last_chart_time is None:
            self._last_chart_time = now
            return None

        elapsed = (now - self._last_chart_time).total_seconds()
        if elapsed >= config.CHART_SAVE_INTERVAL:
            self._last_chart_time = now
            return self._generate_chart(repo)

        return None

    def _generate_chart(self, repo: StraddleRepository) -> str:
        """Generate and save chart."""
        if not self._timestamps:
            return ""

        chart_path = self.chart_gen.generate_chart(
            timestamps=self._timestamps,
            straddle_prices=self._straddle_prices,
            session_id=self._session_id,
            index_name=self.straddle.index_name,
            atm_strike=self.straddle.atm_strike,
            expiry_str=self.straddle.expiry.strftime('%d-%b-%Y')
        )

        # Save chart record
        repo.add_chart(self._session_id, chart_path)

        return chart_path

    async def start(self):
        """
        Start the tracking loop.

        Runs until stopped or market closes.
        """
        self._running = True

        # Create database session
        db_session = get_session()
        repo = StraddleRepository(db_session)

        try:
            # Create tracking session in DB
            session = repo.create_session(
                index_name=self.straddle.index_name,
                expiry_date=self.straddle.expiry,
                atm_strike=Decimal(str(self.straddle.atm_strike))
            )
            self._session_id = session.id

            # Get initial prices
            initial_price = self.calculator.get_initial_prices(
                self.straddle.call_token,
                self.straddle.put_token,
                self.straddle.index_name
            )
            self._call_price = initial_price.call_price
            self._put_price = initial_price.put_price

            # Start WebSocket
            self._start_websocket()

            # Wait for WebSocket to connect
            await asyncio.sleep(1)

            # Main tracking loop
            while self._running:
                # Check market hours
                if not self._is_market_open():
                    print("\nMarket closed. Stopping tracker...")
                    break

                # Get current prices
                if self._call_price is not None and self._put_price is not None:
                    now = datetime.now()

                    # Calculate straddle price
                    straddle_price = self.calculator.calculate_straddle_price(
                        call_price=self._call_price,
                        put_price=self._put_price
                    )

                    # Store for charting
                    self._timestamps.append(now)
                    self._straddle_prices.append(straddle_price.straddle_price)

                    # Save to database
                    self._save_tick(repo, straddle_price)
                    self._tick_count += 1

                    # Callback
                    if self.on_tick:
                        self.on_tick(straddle_price, now)

                    # Maybe generate chart
                    chart_path = self._maybe_generate_chart(repo)
                    if chart_path:
                        print(f"\n[Chart saved: {chart_path}]")

                # Wait 1 second
                await asyncio.sleep(1)

        finally:
            # Cleanup
            self._running = False
            self.kite.stop_ticker()

            # End session
            if self._session_id:
                repo.end_session(self._session_id)

                # Generate final chart
                if self._timestamps:
                    final_chart = self._generate_chart(repo)
                    print(f"\n[Final chart: {final_chart}]")

            db_session.close()

    def stop(self):
        """Stop the tracking loop."""
        self._running = False

    @property
    def tick_count(self) -> int:
        """Number of ticks recorded."""
        return self._tick_count

    @property
    def session_id(self) -> Optional[int]:
        """Current database session ID."""
        return self._session_id


class MarketScheduler:
    """
    Schedules straddle tracking during market hours.
    """

    def __init__(self, tracker: StraddleTracker):
        self.tracker = tracker
        self._shutdown_event = asyncio.Event()

    async def run(self):
        """Run the scheduler until shutdown."""
        # Set up signal handlers
        loop = asyncio.get_event_loop()

        def signal_handler():
            print("\n\nShutting down...")
            self.tracker.stop()
            self._shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            await self.tracker.start()
        except asyncio.CancelledError:
            pass

    def shutdown(self):
        """Initiate shutdown."""
        self.tracker.stop()
        self._shutdown_event.set()
