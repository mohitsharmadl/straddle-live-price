# Straddle Live Price Tracker - The Complete Story

Hey Mohit! This document explains everything about the Straddle Live Price Tracker - a tool I built to track ATM (At-The-Money) straddle prices for NIFTY and SENSEX options in real-time.

## What Does This Project Do?

Imagine you're trading options and want to know the exact price of an ATM straddle (buying both a call and put at the same strike) every single second. This app:

1. **Connects to Zerodha Kite** - Uses their official API to get live prices
2. **Calculates ATM Strike** - Figures out which strike is closest to the current spot price
3. **Tracks Every Second** - Records call + put prices into PostgreSQL
4. **Generates Charts** - Creates beautiful price charts automatically

Think of it like a specialized ticker tape for straddle traders.

---

## The "Big Picture" - How Data Flows

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│   You (CLI)  │────▶│   main.py     │────▶│  Kite OAuth  │
│   "NIFTY"    │     │ Index/Expiry  │     │  (Browser)   │
└──────────────┘     └───────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Calculator  │
                     │  ATM Strike  │
                     └──────────────┘
                            │
                            ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │◀────│  Scheduler   │◀────│  WebSocket   │
│   (Ticks)    │     │  (1 sec loop)│     │  (Live LTP)  │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │    Charts    │
                     │  (Matplotlib)│
                     └──────────────┘
```

**The flow:**
1. You run `python main.py` and pick NIFTY + an expiry
2. App opens browser for Zerodha login (first time each day)
3. Calculator finds the ATM strike (e.g., NIFTY at 23450 → ATM = 23500)
4. WebSocket connects to Kite for real-time prices
5. Every second: CE price + PE price = straddle price → saved to DB
6. Every 30 seconds: chart PNG generated

---

## Project Structure - What Lives Where

```
straddle-live-price/
├── main.py                 # 🚪 Entry point - the CLI you interact with
├── config.py               # ⚙️ All configuration (loads from .env)
├── kite_client.py          # 🔌 Zerodha API wrapper (auth, instruments, WebSocket)
├── straddle_calculator.py  # 🧮 ATM logic + price calculations
├── scheduler.py            # ⏰ The 1-second loop that drives everything
├── db/
│   ├── connection.py       # 🔗 PostgreSQL connection pooling
│   ├── models.py           # 📊 SQLAlchemy tables (Sessions, Ticks, Charts)
│   └── repository.py       # 💾 Data access layer (save/fetch operations)
├── chart/
│   └── generator.py        # 📈 Matplotlib chart generation
├── charts/                 # 📁 Where chart PNGs get saved
├── requirements.txt        # 📦 Python dependencies
├── setup_db.sql           # 🗃️ SQL to create tables
└── .env                    # 🔐 Your secrets (API keys, DB URL)
```

**Entry points to start reading:**
1. `main.py` - Start here to understand the user flow
2. `scheduler.py` - This is where the magic happens (the tracking loop)
3. `kite_client.py` - If you need to understand Kite API integration

---

## Tech Stack & Why These Choices

| Technology | What It Does | Why We Chose It |
|------------|--------------|-----------------|
| **kiteconnect** | Official Zerodha SDK | Only option for Kite API, well-documented |
| **SQLAlchemy** | ORM for PostgreSQL | Clean models, migration-ready, prevents SQL injection |
| **psycopg2** | PostgreSQL driver | Battle-tested, fast, used by SQLAlchemy |
| **matplotlib** | Chart generation | Standard for Python, flexible, no browser needed |
| **rich** | Beautiful CLI output | Makes terminal output actually nice to look at |
| **python-dotenv** | Load .env files | Keep secrets out of code |

**Trade-offs accepted:**
- Using PostgreSQL instead of something like InfluxDB (simpler, but less optimized for time-series)
- Matplotlib over real-time web charts (simpler deployment, but no live updates in browser)
- 1-second polling vs tick-by-tick (easier to manage, slight delay acceptable)

---

## How To Run This

### First-Time Setup

```bash
# 1. Go to project
cd /Users/mohitsharma/straddle-live-price

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env template and fill in your values
cp .env.example .env
# Edit .env with your Kite API key/secret and database URL

# 5. Create PostgreSQL database
createdb straddle_db
psql -d straddle_db -f setup_db.sql

# 6. Run it!
python main.py
```

### Daily Usage

```bash
cd /Users/mohitsharma/straddle-live-price
source venv/bin/activate
python main.py

# Select index (NIFTY/SENSEX)
# Select expiry
# Watch prices flow in!
# Ctrl+C to stop
```

---

## The Database Schema - What Gets Stored

Three tables work together:

### `straddle_sessions` - One row per trading day run
```sql
id          | 1
index_name  | 'NIFTY'
expiry_date | 2026-01-30
atm_strike  | 23500.00
started_at  | 2026-01-28 09:15:00
ended_at    | 2026-01-28 15:30:00
```

### `straddle_ticks` - One row per second (~22,000 rows per full day!)
```sql
id             | 12345
session_id     | 1
timestamp      | 2026-01-28 09:15:01
call_price     | 125.50
put_price      | 120.00
straddle_price | 245.50
spot_price     | 23485.75
```

### `straddle_charts` - Reference to saved chart images
```sql
id           | 10
session_id   | 1
chart_path   | './charts/straddle_1_20260128_093000.png'
generated_at | 2026-01-28 09:30:00
```

---

## Key Code Concepts Explained

### ATM Strike Calculation (`straddle_calculator.py`)

The ATM strike is the strike price closest to the current spot. NIFTY uses 50-point intervals, SENSEX uses 100-point.

```python
def find_atm_strike(self, spot_price: float, index_name: str) -> float:
    interval = 50 if index_name == 'NIFTY' else 100
    # Round to nearest interval
    return round(spot_price / interval) * interval
```

Example: NIFTY spot at 23487 → `round(23487/50)*50` = 23500

### Kite OAuth Flow (`kite_client.py`)

Kite requires browser-based login each day. We:
1. Start a tiny HTTP server on port 8000
2. Open browser to Kite login URL
3. Kite redirects back with a `request_token`
4. We exchange that for an `access_token`
5. Save the token to `.kite_token` for reuse within the day

### The 1-Second Loop (`scheduler.py`)

```python
while self._running:
    if not self._is_market_open():
        break

    # WebSocket already updated _call_price and _put_price
    straddle_price = self._call_price + self._put_price

    # Save to DB
    repo.add_tick(session_id, call, put)

    # Maybe generate chart (every 30 sec)
    if should_generate_chart():
        chart_gen.generate_chart(...)

    await asyncio.sleep(1)
```

---

## Lessons Learned & Gotchas

### 1. Kite Token Expiry
**Problem:** Access tokens expire at end of day, but we were trying to reuse them across days.
**Solution:** Token file stores the date alongside the token. If it's a new day, we force re-login.

### 2. WebSocket vs REST for Prices
**Problem:** Initially used REST API for each price fetch. Hit rate limits.
**Solution:** Switch to WebSocket ticker - one connection, unlimited price updates.

### 3. Database Connection Pooling
**Problem:** Creating new DB connections for each tick was slow.
**Solution:** SQLAlchemy QueuePool - reuse connections, pre-ping to verify they're alive.

### 4. Market Hours Check
**Problem:** App crashed when running outside market hours (no prices).
**Solution:** Added `_is_market_open()` check - gracefully stops if outside 9:15 AM - 3:30 PM IST.

### 5. Matplotlib Thread Safety
**Problem:** Chart generation was blocking the main tick loop.
**Solution:** Generate charts only every 30 seconds, close figures after saving to avoid memory leaks (`plt.close(fig)`).

### 6. Option Symbol Format
**Problem:** Different formats for different indices and expiries.
**Solution:** Let Kite's instrument API tell us the exact `tradingsymbol` instead of constructing it ourselves.

---

## If I Had To Rebuild This...

### What Worked Really Well
- **SQLAlchemy models** - Clean, type-safe, easy to query later
- **Rich CLI** - Makes the terminal output actually enjoyable
- **Separating concerns** - KiteClient, Calculator, Scheduler are independent and testable
- **Token caching** - One login per day is fine for daily trading

### What I'd Do Differently
1. **Add a web dashboard** - A simple FastAPI + React frontend to see live charts in browser
2. **Use InfluxDB** - Better for time-series data, built-in retention policies
3. **Add alerts** - Notify when straddle price moves X% in Y seconds
4. **Multi-expiry tracking** - Track multiple expiries simultaneously
5. **Historical comparison** - Overlay today's straddle curve with yesterday's

---

## Common Queries You Might Run

```sql
-- See all sessions
SELECT * FROM straddle_sessions ORDER BY started_at DESC;

-- Get today's ticks
SELECT timestamp, straddle_price
FROM straddle_ticks
WHERE session_id = (SELECT MAX(id) FROM straddle_sessions)
ORDER BY timestamp;

-- Find high/low of day
SELECT
    MIN(straddle_price) as low,
    MAX(straddle_price) as high,
    MAX(straddle_price) - MIN(straddle_price) as range
FROM straddle_ticks
WHERE session_id = 1;

-- Average straddle price per minute
SELECT
    date_trunc('minute', timestamp) as minute,
    AVG(straddle_price) as avg_price
FROM straddle_ticks
WHERE session_id = 1
GROUP BY 1
ORDER BY 1;
```

---

## Final Notes

This project is a solid foundation for straddle tracking. The code is modular enough that you can:
- Swap PostgreSQL for another database
- Add new indices (BANKNIFTY, etc.)
- Implement different strategies beyond straddles
- Add a web interface later

The key insight: **Straddle prices are a volatility play.** When markets are choppy, straddles are expensive. When markets are flat, they're cheap. By tracking this data over time, you can spot patterns in implied volatility.

Happy trading! 📈

---

*Last updated: January 2026*
