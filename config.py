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
        return missing


config = Config()
