"""
ATM straddle price calculation logic.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from config import config


@dataclass
class StraddleInfo:
    """Information about an ATM straddle position."""
    index_name: str
    expiry: date
    spot_price: float
    atm_strike: float
    call_instrument: dict
    put_instrument: dict
    call_token: int
    put_token: int
    call_symbol: str
    put_symbol: str


@dataclass
class StraddlePrice:
    """Current straddle pricing."""
    call_price: float
    put_price: float
    straddle_price: float
    spot_price: Optional[float] = None


class StraddleCalculator:
    """
    Calculates ATM straddle prices for NIFTY/SENSEX options.

    The ATM (At-The-Money) strike is the strike price closest to the current
    spot price of the underlying index.
    """

    def __init__(self, kite_client):
        """
        Initialize with a KiteClient instance.

        Args:
            kite_client: Authenticated KiteClient instance
        """
        self.kite = kite_client

    def get_strike_interval(self, index_name: str) -> int:
        """Get the strike price interval for an index."""
        if index_name.upper() == 'NIFTY':
            return config.NIFTY_STRIKE_INTERVAL
        elif index_name.upper() == 'SENSEX':
            return config.SENSEX_STRIKE_INTERVAL
        else:
            raise ValueError(f"Unknown index: {index_name}")

    def find_atm_strike(self, spot_price: float, index_name: str) -> float:
        """
        Find the ATM strike price for given spot.

        Rounds to the nearest strike interval.

        Args:
            spot_price: Current spot price of the index
            index_name: 'NIFTY' or 'SENSEX'

        Returns:
            ATM strike price
        """
        interval = self.get_strike_interval(index_name)
        # Round to nearest strike interval
        atm_strike = round(spot_price / interval) * interval
        return float(atm_strike)

    def get_straddle_info(
        self,
        index_name: str,
        expiry: date,
        strike_override: Optional[float] = None
    ) -> StraddleInfo:
        """
        Get complete straddle information for an index and expiry.

        Args:
            index_name: 'NIFTY' or 'SENSEX'
            expiry: Expiry date
            strike_override: Optional specific strike to use instead of ATM

        Returns:
            StraddleInfo with all instrument details
        """
        # Get current spot price
        spot_price = self.kite.get_index_ltp(index_name)

        # Calculate ATM strike
        atm_strike = strike_override or self.find_atm_strike(spot_price, index_name)

        # Find call and put instruments
        call_inst = self.kite.find_option_instrument(
            index_name, expiry, atm_strike, 'CE'
        )
        put_inst = self.kite.find_option_instrument(
            index_name, expiry, atm_strike, 'PE'
        )

        if not call_inst:
            raise ValueError(
                f"Could not find {index_name} {expiry} {atm_strike} CE"
            )
        if not put_inst:
            raise ValueError(
                f"Could not find {index_name} {expiry} {atm_strike} PE"
            )

        return StraddleInfo(
            index_name=index_name.upper(),
            expiry=expiry,
            spot_price=spot_price,
            atm_strike=atm_strike,
            call_instrument=call_inst,
            put_instrument=put_inst,
            call_token=call_inst['instrument_token'],
            put_token=put_inst['instrument_token'],
            call_symbol=call_inst['tradingsymbol'],
            put_symbol=put_inst['tradingsymbol']
        )

    def calculate_straddle_price(
        self,
        call_price: float,
        put_price: float,
        spot_price: Optional[float] = None
    ) -> StraddlePrice:
        """
        Calculate straddle price from component prices.

        Args:
            call_price: Call option LTP
            put_price: Put option LTP
            spot_price: Optional current spot price

        Returns:
            StraddlePrice with all prices
        """
        return StraddlePrice(
            call_price=call_price,
            put_price=put_price,
            straddle_price=call_price + put_price,
            spot_price=spot_price
        )

    def get_initial_prices(
        self,
        call_token: int,
        put_token: int,
        index_name: str
    ) -> StraddlePrice:
        """
        Fetch initial prices for straddle components.

        Used before WebSocket streaming starts.
        """
        prices = self.kite.get_ltp([call_token, put_token])
        spot_price = self.kite.get_index_ltp(index_name)

        call_price = prices.get(call_token, 0)
        put_price = prices.get(put_token, 0)

        return self.calculate_straddle_price(call_price, put_price, spot_price)


def format_option_symbol(
    index_name: str,
    expiry: date,
    strike: float,
    option_type: str
) -> str:
    """
    Format an option symbol in Zerodha format.

    Example: NIFTY26JAN23500CE

    Args:
        index_name: 'NIFTY' or 'SENSEX'
        expiry: Expiry date
        strike: Strike price
        option_type: 'CE' or 'PE'

    Returns:
        Formatted trading symbol
    """
    # Format: INDEX + YY + MMM + STRIKE + TYPE
    year = expiry.strftime('%y')
    month = expiry.strftime('%b').upper()
    strike_str = str(int(strike))

    return f"{index_name.upper()}{year}{month}{strike_str}{option_type}"
