#!/bin/bash
# Market hours scheduler for straddle tracker
# Runs via cron every minute

# Get current IST time (use 10# prefix to force base-10 interpretation)
IST_HOUR=$(TZ='Asia/Kolkata' date +%H)
IST_MIN=$(TZ='Asia/Kolkata' date +%M)
IST_TIME=$((10#$IST_HOUR * 60 + 10#$IST_MIN))
IST_DATE=$(TZ='Asia/Kolkata' date +%Y-%m-%d)
IST_DOW=$(TZ='Asia/Kolkata' date +%u)  # 1=Mon, 7=Sun

# Market hours in minutes from midnight
MARKET_OPEN=$((9 * 60 + 15))   # 9:15 AM = 555 minutes
MARKET_CLOSE=$((15 * 60 + 30)) # 3:30 PM = 930 minutes

# NSE holidays 2026 (weekday closures only)
NSE_HOLIDAYS="2026-01-26 2026-03-03 2026-03-26 2026-03-31 2026-04-03 2026-04-14 2026-05-01 2026-05-28 2026-06-26 2026-09-14 2026-10-02 2026-10-20 2026-11-10 2026-11-24 2026-12-25"

# Check if today is a trading day
IS_TRADING_DAY=true

# Skip weekends (Sat=6, Sun=7)
if [ $IST_DOW -ge 6 ]; then
    IS_TRADING_DAY=false
fi

# Skip NSE holidays
for holiday in $NSE_HOLIDAYS; do
    if [ "$IST_DATE" = "$holiday" ]; then
        IS_TRADING_DAY=false
        break
    fi
done

# Check if tracker is running
TRACKER_RUNNING=$(systemctl is-active straddle-tracker 2>/dev/null)

if [ "$IS_TRADING_DAY" = "true" ] && [ $IST_TIME -ge $MARKET_OPEN ] && [ $IST_TIME -lt $MARKET_CLOSE ]; then
    # Market is open
    if [ "$TRACKER_RUNNING" != "active" ]; then
        echo "$(date): Starting tracker - Market open (IST: ${IST_HOUR}:${IST_MIN})"
        sudo systemctl start straddle-tracker
    fi
else
    # Market is closed or not a trading day
    if [ "$TRACKER_RUNNING" = "active" ]; then
        echo "$(date): Stopping tracker - Market closed (IST: ${IST_HOUR}:${IST_MIN}, trading_day=${IS_TRADING_DAY})"
        sudo systemctl stop straddle-tracker
    fi
fi
