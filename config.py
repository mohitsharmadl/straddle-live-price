"""
Configuration module - loads settings from environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / '.env')


class Config:
    """Application configuration loaded from environment."""

    # Kite API credentials
    KITE_API_KEY: str = os.getenv('KITE_API_KEY', '')
    KITE_API_SECRET: str = os.getenv('KITE_API_SECRET', '')

    # Kite login credentials (for headless auto-login)
    KITE_USER_ID: str = os.getenv('KITE_USER_ID', '')
    KITE_PASSWORD: str = os.getenv('KITE_PASSWORD', '')
    KITE_TOTP_SECRET: str = os.getenv('KITE_TOTP_SECRET', '')

    # Headless mode settings
    HEADLESS_MODE: bool = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
    DEFAULT_INDEX: str = os.getenv('DEFAULT_INDEX', 'NIFTY')
    DEFAULT_EXPIRY_OFFSET: int = int(os.getenv('DEFAULT_EXPIRY_OFFSET', '0'))

    # Database
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'postgresql://localhost:5432/straddle_db')

    # Chart settings
    CHART_SAVE_INTERVAL: int = int(os.getenv('CHART_SAVE_INTERVAL', '30'))
    CHARTS_DIR: Path = Path(os.getenv('CHARTS_DIR', './charts'))

    # Market hours (IST)
    MARKET_OPEN_HOUR: int = 9
    MARKET_OPEN_MINUTE: int = 15
    MARKET_CLOSE_HOUR: int = 15
    MARKET_CLOSE_MINUTE: int = 30

    # Strike intervals
    NIFTY_STRIKE_INTERVAL: int = 50
    SENSEX_STRIKE_INTERVAL: int = 100

    # Token file for storing access token
    TOKEN_FILE: Path = Path(__file__).parent / '.kite_token'

    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration. Returns list of missing fields."""
        missing = []
        if not cls.KITE_API_KEY:
            missing.append('KITE_API_KEY')
        if not cls.KITE_API_SECRET:
            missing.append('KITE_API_SECRET')
        if not cls.DATABASE_URL:
            missing.append('DATABASE_URL')
        # Validate headless login credentials
        if cls.HEADLESS_MODE:
            if not cls.KITE_USER_ID:
                missing.append('KITE_USER_ID')
            if not cls.KITE_PASSWORD:
                missing.append('KITE_PASSWORD')
        return missing


config = Config()
