"""
Zerodha Kite API client wrapper.
Handles authentication, instrument fetching, and real-time price streaming.
"""
import json
import webbrowser
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Callable
import threading

from kiteconnect import KiteConnect, KiteTicker

from config import config


class TokenCaptureHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth redirect with request_token."""
    token = None

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if 'request_token' in query:
            TokenCaptureHandler.token = query['request_token'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
                <html><body style="font-family: Arial; text-align: center; padding-top: 50px;">
                <h1>Login Successful!</h1>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            ''')
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


class KiteClient:
    """
    Wrapper for Zerodha Kite API.

    Handles:
    - OAuth authentication flow
    - Instrument data fetching
    - Real-time price streaming via WebSocket
    """

    def __init__(self):
        self.kite = KiteConnect(api_key=config.KITE_API_KEY)
        self.ticker: Optional[KiteTicker] = None
        self.access_token: Optional[str] = None
        self._instruments_cache: dict = {}
        self._price_callbacks: list[Callable] = []
        self._latest_prices: dict[int, dict] = {}

    def _load_saved_token(self) -> Optional[str]:
        """Load access token from file if valid."""
        if not config.TOKEN_FILE.exists():
            return None

        try:
            data = json.loads(config.TOKEN_FILE.read_text())
            # Check if token is from today
            if data.get('date') == str(date.today()):
                return data.get('access_token')
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def _save_token(self, access_token: str):
        """Save access token to file."""
        config.TOKEN_FILE.write_text(json.dumps({
            'access_token': access_token,
            'date': str(date.today())
        }))

    def authenticate(self, force_login: bool = False) -> bool:
        """
        Authenticate with Kite API.

        If a valid token exists from today, reuses it.
        Otherwise, opens browser for OAuth login.

        Returns True if authentication successful.
        """
        # Try to reuse existing token
        if not force_login:
            saved_token = self._load_saved_token()
            if saved_token:
                self.access_token = saved_token
                self.kite.set_access_token(saved_token)
                try:
                    # Verify token is still valid
                    self.kite.profile()
                    return True
                except Exception:
                    pass  # Token invalid, proceed with login

        # Start local server to capture redirect
        server = HTTPServer(('127.0.0.1', 8000), TokenCaptureHandler)
        server.timeout = 120  # 2 minute timeout

        # Generate login URL
        login_url = self.kite.login_url()
        print(f"\nOpening browser for Kite login...")
        print(f"If browser doesn't open, visit: {login_url}\n")
        webbrowser.open(login_url)

        # Wait for redirect with token
        TokenCaptureHandler.token = None
        while TokenCaptureHandler.token is None:
            server.handle_request()

        request_token = TokenCaptureHandler.token
        server.server_close()

        # Exchange request token for access token
        try:
            data = self.kite.generate_session(
                request_token,
                api_secret=config.KITE_API_SECRET
            )
            self.access_token = data['access_token']
            self.kite.set_access_token(self.access_token)
            self._save_token(self.access_token)
            return True
        except Exception as e:
            print(f"Authentication failed: {e}")
            return False

    def get_profile(self) -> dict:
        """Get user profile information."""
        return self.kite.profile()

    def get_instruments(self, exchange: str = 'NFO') -> list[dict]:
        """
        Fetch all instruments for an exchange.
        Results are cached for the session.
        """
        if exchange not in self._instruments_cache:
            self._instruments_cache[exchange] = self.kite.instruments(exchange)
        return self._instruments_cache[exchange]

    def get_index_instruments(self, index_name: str) -> list[dict]:
        """
        Get all option instruments for an index (NIFTY or SENSEX).
        """
        instruments = self.get_instruments('NFO')

        # Map index names to underlying names in Kite
        name_map = {
            'NIFTY': 'NIFTY',
            'SENSEX': 'SENSEX'
        }
        underlying = name_map.get(index_name.upper(), index_name.upper())

        return [
            inst for inst in instruments
            if inst['name'] == underlying and inst['instrument_type'] in ('CE', 'PE')
        ]

    def get_expiries(self, index_name: str) -> list[date]:
        """Get available expiry dates for an index, sorted ascending."""
        instruments = self.get_index_instruments(index_name)
        expiries = sorted(set(inst['expiry'] for inst in instruments))
        return expiries

    def get_ltp(self, instrument_tokens: list[int]) -> dict[int, float]:
        """Get last traded price for instruments."""
        if not instrument_tokens:
            return {}

        # Kite API expects exchange:token format for quotes
        # We'll use the ticker for real-time, this is for initial fetch
        quotes = self.kite.ltp([f"NFO:{token}" for token in instrument_tokens])
        return {
            int(key.split(':')[1]): data['last_price']
            for key, data in quotes.items()
        }

    def get_index_ltp(self, index_name: str) -> float:
        """Get current spot price for an index."""
        index_map = {
            'NIFTY': 'NSE:NIFTY 50',
            'SENSEX': 'BSE:SENSEX'
        }
        symbol = index_map.get(index_name.upper())
        if not symbol:
            raise ValueError(f"Unknown index: {index_name}")

        quote = self.kite.ltp([symbol])
        return quote[symbol]['last_price']

    def find_option_instrument(
        self,
        index_name: str,
        expiry: date,
        strike: float,
        option_type: str  # 'CE' or 'PE'
    ) -> Optional[dict]:
        """Find a specific option instrument."""
        instruments = self.get_index_instruments(index_name)

        for inst in instruments:
            if (inst['expiry'] == expiry and
                inst['strike'] == strike and
                inst['instrument_type'] == option_type):
                return inst

        return None

    def start_ticker(
        self,
        instrument_tokens: list[int],
        on_price_update: Callable[[dict], None]
    ):
        """
        Start WebSocket ticker for real-time prices.

        on_price_update receives dict with:
        - instrument_token: int
        - last_price: float
        - timestamp: datetime
        """
        self.ticker = KiteTicker(config.KITE_API_KEY, self.access_token)

        def on_ticks(ws, ticks):
            for tick in ticks:
                self._latest_prices[tick['instrument_token']] = tick
                on_price_update({
                    'instrument_token': tick['instrument_token'],
                    'last_price': tick['last_price'],
                    'timestamp': tick.get('timestamp', datetime.now())
                })

        def on_connect(ws, response):
            ws.subscribe(instrument_tokens)
            ws.set_mode(ws.MODE_LTP, instrument_tokens)

        def on_close(ws, code, reason):
            pass

        def on_error(ws, code, reason):
            print(f"Ticker error: {code} - {reason}")

        self.ticker.on_ticks = on_ticks
        self.ticker.on_connect = on_connect
        self.ticker.on_close = on_close
        self.ticker.on_error = on_error

        # Run ticker in background thread
        ticker_thread = threading.Thread(target=self.ticker.connect, daemon=True)
        ticker_thread.start()

    def stop_ticker(self):
        """Stop the WebSocket ticker."""
        if self.ticker:
            self.ticker.close()
            self.ticker = None

    def get_latest_price(self, instrument_token: int) -> Optional[float]:
        """Get latest cached price for an instrument."""
        tick = self._latest_prices.get(instrument_token)
        return tick['last_price'] if tick else None
