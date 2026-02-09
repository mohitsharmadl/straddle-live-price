#!/usr/bin/env python3
"""
Refresh Kite access token via headless login.
Run via cron at 9:00 AM IST daily before market open.
Token is saved to .kite_token and used by both straddle tracker and PnL collector.
"""
import sys
import os

# Add straddle-live-price to path so we can reuse its modules
sys.path.insert(0, os.path.expanduser('~/projects/straddle-live-price'))

from kite_client import KiteClient

def main():
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
