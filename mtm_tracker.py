"""
MTM (Mark-to-Market) tracker for Kite holdings.
Polls holdings every 5 seconds during market hours,
records day PnL to PostgreSQL, and sends Telegram chart at EOD.
"""
import json
import time
import logging
import requests
import psycopg2
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect
from config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
POLL_INTERVAL = 1  # seconds
DB_URL = "postgresql://ubuntu:straddle123@localhost:5432/trading_bot"
TELEGRAM_BOT_TOKEN = "8524854621:AAGyhRZqsRH1nnShrCtG2WfzaAXoA8fXXQ4"
TELEGRAM_CHAT_ID = "665202127"
CHARTS_DIR = Path(__file__).parent / "mtm_charts"


def ist_now():
    return datetime.now(IST)


def is_market_open():
    now = ist_now()
    if now.weekday() > 4:
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


def get_db():
    return psycopg2.connect(DB_URL)


def _try_load_token():
    """Return an authenticated KiteConnect or None if no valid token exists today."""
    kite = KiteConnect(api_key=config.KITE_API_KEY)
    token_file = config.TOKEN_FILE
    if not token_file.exists():
        return None
    try:
        data = json.loads(token_file.read_text())
    except Exception:
        return None
    if data.get('date') != str(date.today()):
        return None
    kite.set_access_token(data['access_token'])
    try:
        kite.profile()
        return kite
    except Exception:
        return None


def load_kite():
    """Wait for a valid Kite token and return an authenticated client.

    Polls every 60s instead of exiting, so when Kite re-auth happens
    (subscription renewal, daily token refresh) the writer auto-recovers
    without manual restart.
    """
    logged_waiting = False
    while True:
        kite = _try_load_token()
        if kite:
            logger.info("Kite auth: reused today's token")
            return kite
        if not logged_waiting:
            logger.warning(
                "No valid Kite token for today. Waiting for kite_token_refresh "
                "(or straddle-tracker) to write one. Polling every 60s."
            )
            logged_waiting = True
        time.sleep(60)


# ── WebSocket-based holdings PnL tracking ──
_holdings_info = {}      # {instrument_token: {symbol, qty, close_price, exchange_key}}
_holdings_ltp = {}       # {instrument_token: last_price} -- updated by WebSocket
_holdings_initialized = False
_holdings_ws_started = False

def init_holdings_tracking(kite):
    """Initialize holdings info and start WebSocket for real-time LTP."""
    global _holdings_info, _holdings_ltp, _holdings_initialized, _holdings_ws_started

    holdings = kite.holdings()
    instruments_for_ws = []

    for h in holdings:
        symbol = h["tradingsymbol"]
        qty = h.get("quantity", 0) + h.get("t1_quantity", 0) + h.get("collateral_quantity", 0)
        if qty == 0:
            continue
        token = h.get("instrument_token", 0)
        if not token:
            continue
        close_price = h.get("close_price", 0) or 0
        exchange = h.get("exchange", "NSE")

        _holdings_info[token] = {
            "symbol": symbol,
            "qty": qty,
            "close_price": close_price,
            "exchange": exchange,
        }
        _holdings_ltp[token] = h.get("last_price", close_price) or close_price
        instruments_for_ws.append(token)

    _holdings_initialized = True
    logger.info(f"Holdings tracking initialized: {len(instruments_for_ws)} stocks")

    # Start WebSocket in a background thread for holdings
    if instruments_for_ws and not _holdings_ws_started:
        import threading
        from kiteconnect import KiteTicker

        def _run_ws():
            global _holdings_ws_started
            _holdings_ws_started = True
            ticker = KiteTicker(config.KITE_API_KEY, kite.access_token)

            _tick_count = [0]
            def on_ticks(ws, ticks):
                _tick_count[0] += 1
                for tick in ticks:
                    token = tick["instrument_token"]
                    if token in _holdings_ltp:
                        _holdings_ltp[token] = tick["last_price"]
                if _tick_count[0] % 50 == 0:
                    print(f"[Holdings WS] {_tick_count[0]} tick batches received, {len(ticks)} ticks in last batch")
            def on_connect(ws, response):
                logger.info(f"[Holdings WS connected] Subscribing {len(instruments_for_ws)} tokens")
                ws.subscribe(instruments_for_ws)
                ws.set_mode(ws.MODE_QUOTE, instruments_for_ws)

            def on_close(ws, code, reason):
                global _holdings_ws_started
                logger.warning(f"[Holdings WS closed: {code} - {reason}]")
                _holdings_ws_started = False

            def on_error(ws, code, reason):
                logger.error(f"[Holdings WS error: {code} - {reason}]")

            ticker.on_ticks = on_ticks
            ticker.on_connect = on_connect
            ticker.on_close = on_close
            ticker.on_error = on_error
            ticker.connect(threaded=False)

        ws_thread = threading.Thread(target=_run_ws, daemon=True)
        ws_thread.start()
        logger.info("Holdings WebSocket thread started")

    return instruments_for_ws


def get_holdings_pnl(kite):
    """Get total day PnL using WebSocket-streamed LTP for true per-second accuracy."""
    global _holdings_initialized

    if not _holdings_initialized:
        print(f"[Holdings] Initializing WebSocket tracking...")
        init_holdings_tracking(kite)

    total_day_pnl = 0.0
    stocks = {}

    for token, info in _holdings_info.items():
        ltp = _holdings_ltp.get(token, 0)
        close = info["close_price"]
        qty = info["qty"]

        if ltp and close:
            stock_day_pnl = (ltp - close) * qty
        else:
            stock_day_pnl = 0

        total_day_pnl += stock_day_pnl
        stocks[info["symbol"]] = round(stock_day_pnl, 2)

    return round(total_day_pnl, 2), stocks

    for key, info in holdings_map.items():
        q = quotes.get(key, {})
        ltp = q.get("last_price", 0)
        close = info["close_price"]
        qty = info["qty"]

        if ltp and close:
            stock_day_pnl = (ltp - close) * qty
        else:
            stock_day_pnl = 0
        total_day_pnl += stock_day_pnl
        stocks[info["symbol"]] = round(stock_day_pnl, 2)

    return round(total_day_pnl, 2), stocks


def record_tick(now, total_pnl, stocks):
    """Insert a row into holdings_pnl_snapshots."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO holdings_pnl_snapshots (date, timestamp, total_pnl, stocks_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (date, timestamp) DO UPDATE SET
                total_pnl = EXCLUDED.total_pnl,
                stocks_json = EXCLUDED.stocks_json
        """, (now.date(), now.strftime('%H:%M:%S'), total_pnl, json.dumps(stocks)))
        conn.commit()
    finally:
        conn.close()


def generate_chart(today_str, chart_path):
    """Generate MTM chart from DB data."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT timestamp, total_pnl FROM holdings_pnl_snapshots
            WHERE date = %s ORDER BY timestamp ASC
        """, (today_str,))
        rows = cur.fetchall()
    finally:
        conn.close()

    if len(rows) < 2:
        logger.warning("Not enough data points to generate chart")
        return None

    # Sample every 10 seconds to reduce points
    times = []
    pnls = []
    for t, p in rows:
        total_seconds = t.total_seconds()
        if not times or (total_seconds - times[-1]) >= 10:
            times.append(total_seconds)
            pnls.append(float(p))

    # Convert seconds to HH:MM labels
    labels = []
    for s in times:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        labels.append(f"{h:02d}:{m:02d}")

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axhline(y=0, color='gray', linewidth=0.5, linestyle='--')

    ax.fill_between(range(len(pnls)), pnls, 0,
                     where=[p >= 0 for p in pnls],
                     color='#22c55e', alpha=0.15)
    ax.fill_between(range(len(pnls)), pnls, 0,
                     where=[p < 0 for p in pnls],
                     color='#ef4444', alpha=0.15)

    line_color = '#22c55e' if pnls[-1] >= 0 else '#ef4444'
    ax.plot(range(len(pnls)), pnls, color=line_color, linewidth=1.5)

    final_pnl = pnls[-1]
    sign = '+' if final_pnl >= 0 else ''
    ax.set_title(f'Holdings MTM — {today_str}  |  Day PnL: {sign}{final_pnl:,.0f}',
                 fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel('Day PnL (INR)', fontsize=11)

    # Show ~10 time labels
    step = max(len(labels) // 10, 1)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)], fontsize=9)

    ax.grid(True, alpha=0.3)
    ax.set_facecolor('#ffffff')
    fig.patch.set_facecolor('#ffffff')

    plt.tight_layout()
    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    plt.close()

    logger.info(f"Chart saved: {chart_path}")
    return chart_path


def send_telegram_photo(photo_path, caption=""):
    """Send chart image via Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as f:
        resp = requests.post(url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'caption': caption
        }, files={'photo': f})
    if resp.status_code == 200:
        logger.info("Chart sent to Telegram")
    else:
        logger.error(f"Telegram send failed: {resp.text}")


def run():
    CHARTS_DIR.mkdir(exist_ok=True)

    kite = load_kite()
    today_str = date.today().strftime('%Y-%m-%d')

    logger.info("MTM tracker started. Waiting for market open...")

    chart_sent = False

    while True:
        now = ist_now()

        if is_market_open():
            try:
                total_pnl, stocks = get_holdings_pnl(kite)
                record_tick(now, total_pnl, stocks)

                if now.second < POLL_INTERVAL:
                    sign = '+' if total_pnl >= 0 else ''
                    logger.info(f"Day PnL: {sign}{total_pnl:,.0f}")

            except Exception as e:
                logger.error(f"Error fetching holdings: {e}", exc_info=True)

            chart_sent = False
            time.sleep(POLL_INTERVAL)

        elif now.hour == 15 and now.minute >= 30 and not chart_sent:
            logger.info("Market closed. Generating chart...")
            chart_path = CHARTS_DIR / f"mtm_{today_str}.png"
            result = generate_chart(today_str, chart_path)
            if result:
                try:
                    total_pnl, stocks = get_holdings_pnl(kite)
                    sorted_stocks = sorted(stocks.items(), key=lambda x: abs(x[1]), reverse=True)
                    top = sorted_stocks[:5]
                    lines = [f"Holdings MTM — {today_str}",
                             f"Day PnL: {'+'if total_pnl>=0 else ''}{total_pnl:,.0f}",
                             "", "Top movers:"]
                    for sym, pnl in top:
                        s = '+' if pnl >= 0 else ''
                        lines.append(f"  {sym}: {s}{pnl:,.0f}")
                    caption = '\n'.join(lines)
                except Exception:
                    caption = f"Holdings MTM — {today_str}"
                send_telegram_photo(chart_path, caption)
            chart_sent = True
            logger.info("Done for today. Exiting.")
            break

        else:
            if now.hour < 9 or (now.hour == 9 and now.minute < 15):
                time.sleep(30)
            else:
                logger.info("Market closed. Exiting.")
                break


if __name__ == '__main__':
    run()
