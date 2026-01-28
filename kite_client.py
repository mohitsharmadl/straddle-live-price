"""
Zerodha Kite API client wrapper.
Handles authentication, instrument fetching, and real-time price streaming.
Supports headless auto-login with Playwright.
"""
import json
import webbrowser
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Callable
import threading
import time
import logging

from kiteconnect import KiteConnect, KiteTicker

from config import config

# Configure logging
logger = logging.getLogger(__name__)

# OAuth timeout in seconds (2 minutes)
OAUTH_TIMEOUT_SECONDS = 120

# Optional imports for headless login
try:
    from playwright.sync_api import sync_playwright
    import pyotp
    HEADLESS_AVAILABLE = True
except ImportError:
    HEADLESS_AVAILABLE = False


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

        # WebSocket reconnection state
        self._ticker_should_run = False
        self._ticker_tokens: list[int] = []
        self._ticker_callback: Optional[Callable] = None
        self._ticker_reconnect_count = 0
        self._ticker_max_reconnects = 10

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

        # Use headless login if configured and available
        if config.HEADLESS_MODE and HEADLESS_AVAILABLE:
            return self._headless_login()

        # Fall back to browser-based login
        return self._browser_login()

    def _browser_login(self) -> bool:
        """Traditional browser-based OAuth login with overall timeout."""
        # Start local server to capture redirect
        server = HTTPServer(('127.0.0.1', 8000), TokenCaptureHandler)
        server.timeout = 5  # 5 second timeout per request

        # Generate login URL
        login_url = self.kite.login_url()
        print(f"\nOpening browser for Kite login...")
        print(f"If browser doesn't open, visit: {login_url}")
        print(f"(Timeout: {OAUTH_TIMEOUT_SECONDS} seconds)\n")
        webbrowser.open(login_url)

        # Wait for redirect with token (with overall timeout)
        TokenCaptureHandler.token = None
        start_time = time.time()

        while TokenCaptureHandler.token is None:
            # Check overall timeout
            elapsed = time.time() - start_time
            if elapsed >= OAUTH_TIMEOUT_SECONDS:
                print(f"\nOAuth login timed out after {OAUTH_TIMEOUT_SECONDS} seconds.")
                server.server_close()
                return False

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

    def _headless_login(self) -> bool:
        """
        Headless browser login using Playwright.
        Automatically fills credentials and handles TOTP.
        """
        print("Starting headless auto-login...")

        login_url = self.kite.login_url()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            # Set up early request monitoring to capture redirect URL
            captured_token = {'value': None}

            def capture_redirect(request):
                url = request.url
                if 'request_token=' in url and not captured_token['value']:
                    import re
                    match = re.search(r'request_token=([^&]+)', url)
                    if match:
                        captured_token['value'] = match.group(1)
                        print(f"Captured request token from redirect!")

            page.on('request', capture_redirect)

            try:
                # Navigate to login page
                print("Navigating to Kite login...")
                page.goto(login_url, wait_until='networkidle', timeout=30000)
                time.sleep(2)

                # Fill user ID - try multiple selectors
                print(f"Entering User ID: {config.KITE_USER_ID}")
                userid_selectors = [
                    'input#userid',
                    'input[type="text"]',
                    'input[placeholder*="User"]',
                    'input[name="user_id"]',
                ]
                for selector in userid_selectors:
                    try:
                        if page.locator(selector).first.is_visible(timeout=2000):
                            page.fill(selector, config.KITE_USER_ID)
                            break
                    except:
                        continue

                # Fill password - try multiple selectors
                print("Entering password...")
                password_selectors = [
                    'input#password',
                    'input[type="password"]',
                    'input[placeholder*="Password"]',
                    'input[name="password"]',
                ]
                for selector in password_selectors:
                    try:
                        if page.locator(selector).first.is_visible(timeout=2000):
                            page.fill(selector, config.KITE_PASSWORD)
                            break
                    except:
                        continue

                # Click login button
                print("Clicking login button...")
                submit_selectors = [
                    'button[type="submit"]',
                    'button.button-orange',
                    'button:has-text("Login")',
                    'input[type="submit"]',
                ]
                for selector in submit_selectors:
                    try:
                        if page.locator(selector).first.is_visible(timeout=2000):
                            page.click(selector)
                            break
                    except:
                        continue

                time.sleep(3)

                # Handle TOTP if configured
                if config.KITE_TOTP_SECRET:
                    totp = pyotp.TOTP(config.KITE_TOTP_SECRET)
                    totp_code = totp.now()
                    print(f"Entering TOTP code...")

                    # Wait for TOTP input field
                    totp_selectors = [
                        'input[type="number"]',
                        'input[type="text"]:visible',
                        'input#totp',
                        'input[placeholder*="TOTP"]',
                        'input[placeholder*="OTP"]',
                        'input.su-input-group',
                    ]

                    totp_entered = False
                    for selector in totp_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=5000)
                            if page.locator(selector).first.is_visible():
                                page.fill(selector, totp_code)
                                totp_entered = True
                                break
                        except:
                            continue

                    if not totp_entered:
                        # Try filling any visible input
                        page.locator('input:visible').first.fill(totp_code)

                    time.sleep(1)

                    # Click continue/submit for TOTP
                    for selector in submit_selectors:
                        try:
                            if page.locator(selector).first.is_visible(timeout=2000):
                                page.click(selector)
                                break
                        except:
                            continue

                    time.sleep(3)

                # Handle app authorization screen (secondary password prompt)
                # This screen appears after TOTP for third-party app authorization
                try:
                    # Check if there's another password field (app authorization)
                    auth_password_field = page.locator('input[type="password"], input[placeholder*="password" i]').first
                    if auth_password_field.is_visible(timeout=3000):
                        print("Handling app authorization - entering password again...")
                        auth_password_field.fill(config.KITE_PASSWORD)
                        time.sleep(1)

                        # Click authorize/continue button
                        auth_button_selectors = [
                            'button[type="submit"]',
                            'button:has-text("Authorize")',
                            'button:has-text("Continue")',
                            'button.button-orange',
                        ]
                        for selector in auth_button_selectors:
                            try:
                                btn = page.locator(selector).first
                                if btn.is_visible(timeout=1000):
                                    btn.click()
                                    break
                            except:
                                continue
                        time.sleep(3)
                except:
                    pass  # No app authorization screen

                # Wait for redirect and capture request_token
                print("Waiting for redirect with request token...")

                # Wait and poll for request_token (captured by earlier listener)
                max_attempts = 30
                for attempt in range(max_attempts):
                    if captured_token['value']:
                        break
                    # Also check current URL
                    current_url = page.url
                    if 'request_token=' in current_url:
                        import re
                        match = re.search(r'request_token=([^&]+)', current_url)
                        if match:
                            captured_token['value'] = match.group(1)
                            print(f"Got request token from URL!")
                            break
                    time.sleep(1)

                request_token = captured_token['value']

                if not request_token:
                    print(f"Failed to get request_token after {max_attempts}s. Final URL: {page.url}")
                    page.screenshot(path='/tmp/login_final_state.png')
                    return False

                print("Exchanging request token for access token...")

            except Exception as e:
                print(f"Headless login error: {e}")
                # Take screenshot for debugging
                try:
                    page.screenshot(path='/tmp/login_error.png')
                    print("Screenshot saved to /tmp/login_error.png")
                except:
                    pass
                return False
            finally:
                browser.close()

        # Exchange request token for access token
        try:
            data = self.kite.generate_session(
                request_token,
                api_secret=config.KITE_API_SECRET
            )
            self.access_token = data['access_token']
            self.kite.set_access_token(self.access_token)
            self._save_token(self.access_token)
            print("Headless login successful!")
            return True
        except Exception as e:
            print(f"Session generation failed: {e}")
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
        NIFTY options are on NFO (NSE), SENSEX options are on BFO (BSE).
        """
        # Map index to exchange and underlying name
        index_config = {
            'NIFTY': {'exchange': 'NFO', 'name': 'NIFTY'},
            'SENSEX': {'exchange': 'BFO', 'name': 'SENSEX'}
        }

        config_entry = index_config.get(index_name.upper())
        if not config_entry:
            return []

        exchange = config_entry['exchange']
        underlying = config_entry['name']

        instruments = self.get_instruments(exchange)

        return [
            inst for inst in instruments
            if inst['name'] == underlying and inst['instrument_type'] in ('CE', 'PE')
        ]

    def get_expiries(self, index_name: str) -> list[date]:
        """Get available expiry dates for an index, sorted ascending."""
        instruments = self.get_index_instruments(index_name)
        expiries = sorted(set(inst['expiry'] for inst in instruments))
        return expiries

    def get_ltp_by_symbol(self, trading_symbols: list[str], exchange: str = 'NFO') -> dict[str, float]:
        """
        Get last traded price for instruments by trading symbol.

        Args:
            trading_symbols: List of trading symbols (e.g., ['NIFTY26JAN23500CE', 'NIFTY26JAN23500PE'])
            exchange: Exchange code ('NFO' for NIFTY, 'BFO' for SENSEX)

        Returns:
            Dict mapping trading symbol to last price
        """
        if not trading_symbols:
            return {}

        # Kite LTP API expects exchange:tradingsymbol format
        symbols_with_exchange = [f"{exchange}:{symbol}" for symbol in trading_symbols]

        try:
            quotes = self.kite.ltp(symbols_with_exchange)
            return {
                key.split(':')[1]: data['last_price']
                for key, data in quotes.items()
            }
        except Exception as e:
            logger.warning(f"Failed to fetch LTP for {trading_symbols}: {e}")
            return {}

    def get_exchange_for_index(self, index_name: str) -> str:
        """Get the exchange for an index (NFO for NIFTY, BFO for SENSEX)."""
        exchange_map = {
            'NIFTY': 'NFO',
            'SENSEX': 'BFO'
        }
        return exchange_map.get(index_name.upper(), 'NFO')

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

        Automatically reconnects on disconnect with exponential backoff.
        """
        self._ticker_tokens = instrument_tokens
        self._ticker_callback = on_price_update
        self._ticker_reconnect_count = 0
        self._ticker_max_reconnects = 10
        self._ticker_should_run = True

        self._start_ticker_internal()

    def _start_ticker_internal(self):
        """Internal method to start/restart the ticker."""
        self.ticker = KiteTicker(config.KITE_API_KEY, self.access_token)

        def on_ticks(ws, ticks):
            # Reset reconnect count on successful tick
            self._ticker_reconnect_count = 0
            for tick in ticks:
                self._latest_prices[tick['instrument_token']] = tick
                self._ticker_callback({
                    'instrument_token': tick['instrument_token'],
                    'last_price': tick['last_price'],
                    'timestamp': tick.get('timestamp', datetime.now())
                })

        def on_connect(ws, response):
            print(f"[WebSocket connected]")
            ws.subscribe(self._ticker_tokens)
            ws.set_mode(ws.MODE_LTP, self._ticker_tokens)

        def on_close(ws, code, reason):
            if not self._ticker_should_run:
                return  # Intentional close, don't reconnect

            print(f"[WebSocket closed: {code} - {reason}]")
            self._attempt_reconnect()

        def on_error(ws, code, reason):
            print(f"[WebSocket error: {code} - {reason}]")
            # Error will trigger on_close, which handles reconnection

        self.ticker.on_ticks = on_ticks
        self.ticker.on_connect = on_connect
        self.ticker.on_close = on_close
        self.ticker.on_error = on_error

        # Run ticker in background thread
        ticker_thread = threading.Thread(target=self.ticker.connect, daemon=True)
        ticker_thread.start()

    def _attempt_reconnect(self):
        """Attempt to reconnect the WebSocket with exponential backoff."""
        if not self._ticker_should_run:
            return

        if self._ticker_reconnect_count >= self._ticker_max_reconnects:
            print(f"[WebSocket max reconnects ({self._ticker_max_reconnects}) reached, giving up]")
            return

        self._ticker_reconnect_count += 1
        # Exponential backoff: 1s, 2s, 4s, 8s, ... capped at 30s
        delay = min(2 ** (self._ticker_reconnect_count - 1), 30)
        print(f"[WebSocket reconnecting in {delay}s (attempt {self._ticker_reconnect_count}/{self._ticker_max_reconnects})]")

        def reconnect():
            import time
            time.sleep(delay)
            if self._ticker_should_run:
                self._start_ticker_internal()

        reconnect_thread = threading.Thread(target=reconnect, daemon=True)
        reconnect_thread.start()

    def stop_ticker(self):
        """Stop the WebSocket ticker."""
        self._ticker_should_run = False  # Prevent reconnection attempts
        if self.ticker:
            self.ticker.close()
            self.ticker = None

    def get_latest_price(self, instrument_token: int) -> Optional[float]:
        """Get latest cached price for an instrument."""
        tick = self._latest_prices.get(instrument_token)
        return tick['last_price'] if tick else None
