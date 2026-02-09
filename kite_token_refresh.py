#!/usr/bin/env python3
"""
Refresh Kite access token via headless login.
Run via cron at 9:00 AM IST daily (weekdays). Skips NSE holidays.
Token is saved to .kite_token and used by both straddle tracker and PnL collector.
"""
import sys
import os
from datetime import date, datetime, timezone, timedelta

# Add straddle-live-price to path so we can reuse its modules
sys.path.insert(0, os.path.expanduser('~/projects/straddle-live-price'))

IST = timezone(timedelta(hours=5, minutes=30))

NSE_HOLIDAYS_2026 = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 3),    # Holi
    date(2026, 3, 26),   # Ram Navami
    date(2026, 3, 31),   # Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 28),   # Eid ul-Adha
    date(2026, 6, 26),   # Muharram
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dasara
    date(2026, 11, 10),  # Diwali-Balipratipada
    date(2026, 11, 24),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}

def main():
    today = datetime.now(IST).date()

    if today in NSE_HOLIDAYS_2026:
        print(f"Skipping token refresh - {today} is an NSE holiday")
        return 0

    from kite_client import KiteClient

    client = KiteClient()
    print("Refreshing Kite access token (headless login)...")

    if client.authenticate(force_login=True):
        profile = client.get_profile()
        print(f"Token refreshed successfully! Logged in as: {profile['user_name']}")
        return 0
    else:
        print("ERROR: Token refresh failed!")
        return 1

if __name__ == '__main__':
    sys.exit(main())
