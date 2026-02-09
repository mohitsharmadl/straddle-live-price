#!/bin/bash
# Market hours scheduler for straddle tracker
# Runs via cron every minute

# Get current IST time (use 10# prefix to force base-10 interpretation)
IST_HOUR=$(TZ='Asia/Kolkata' date +%H)
IST_MIN=$(TZ='Asia/Kolkata' date +%M)
IST_TIME=$((10#$IST_HOUR * 60 + 10#$IST_MIN))

# Market hours in minutes from midnight
MARKET_OPEN=$((9 * 60 + 15))   # 9:15 AM = 555 minutes
MARKET_CLOSE=$((15 * 60 + 30)) # 3:30 PM = 930 minutes

# Check if tracker is running
TRACKER_RUNNING=$(systemctl is-active straddle-tracker 2>/dev/null)

if [ $IST_TIME -ge $MARKET_OPEN ] && [ $IST_TIME -lt $MARKET_CLOSE ]; then
    # Market is open
    if [ "$TRACKER_RUNNING" != "active" ]; then
        echo "$(date): Starting tracker - Market open (IST: ${IST_HOUR}:${IST_MIN})"
        sudo systemctl start straddle-tracker
    fi
else
    # Market is closed
    if [ "$TRACKER_RUNNING" = "active" ]; then
        echo "$(date): Stopping tracker - Market closed (IST: ${IST_HOUR}:${IST_MIN})"
        sudo systemctl stop straddle-tracker
    fi
fi
