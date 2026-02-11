# Straddle Live Price Tracker

Real-time ATM (At-The-Money) straddle price tracker for **NIFTY** and **SENSEX** options. Captures call + put prices every second during Indian market hours (9:15 AM - 3:30 PM IST) using the Zerodha Kite API, stores them in PostgreSQL, and generates intraday charts.

## What It Does

1. **Authenticates** with Zerodha Kite via headless Playwright-based auto-login (TOTP supported)
2. **Auto-selects** the nearest expiry across NIFTY and SENSEX (0 DTE > 1 DTE > 2 DTE)
3. **Streams prices** via Kite WebSocket at ~1 tick/second
4. **Dynamically adjusts** the ATM strike when the spot price moves (NIFTY: 50-pt intervals, SENSEX: 100-pt)
5. **Stores every tick** in PostgreSQL (`straddle_db`)
6. **Generates chart PNGs** every 30 seconds (old charts cleaned up hourly, only latest kept)
7. **Feeds data** to the dashboard at [dashboard.mohitsharma.com](https://dashboard.mohitsharma.com)

## Architecture

```
                     +----------------+
                     |  Zerodha Kite  |
                     |   (OAuth2 +    |
                     |   WebSocket)   |
                     +-------+--------+
                             | Live option prices
                             v
+----------+    +------------------------+    +--------------+
|  Cron    |--->|      main.py           |--->|  PostgreSQL  |
| market-  |    |  +------------------+  |    | straddle_db  |
|scheduler |    |  | straddle_calc.py |  |    |  - sessions  |
|  .sh     |    |  |  (ATM strike)    |  |    |  - ticks     |
|          |    |  +------------------+  |    |  - charts    |
| (start/  |    |  +------------------+  |    +------+-------+
|  stop)   |    |  |  scheduler.py    |  |           |
+----------+    |  |  (1s tick loop)  |  |           v
                |  +------------------+  |    +--------------+
+----------+    |  +------------------+  |    |  Dashboard   |
| kite_    |    |  |  chart/          |--+--->|  (FastAPI)   |
| token_   |    |  |  generator.py    |  |    | mohitsharma  |
| refresh  |    |  +------------------+  |    |   .com       |
| .py      |    +------------------------+    +--------------+
| (9AM IST)|
+----------+
```

## Project Structure

```
straddle-live-price/
├── main.py                    # Entry point - CLI with headless and interactive modes
├── config.py                  # Configuration from .env (API keys, DB URL, market hours)
├── kite_client.py             # Zerodha Kite wrapper: OAuth, instruments, WebSocket ticker
├── straddle_calculator.py     # ATM strike calculation and straddle pricing logic
├── scheduler.py               # Core 1-second tracking loop with strike switching
├── market-scheduler.sh        # Cron script: start/stop tracker based on IST market hours
├── kite_token_refresh.py      # Daily 9:00 AM IST headless token refresh (skips holidays)
├── db/
│   ├── __init__.py            # Exports init_db, get_session, StraddleRepository
│   ├── connection.py          # SQLAlchemy engine with QueuePool (pool_size=5)
│   ├── models.py              # ORM models: StraddleSession, StraddleTick, StraddleChart
│   └── repository.py          # Data access: batched tick inserts, session resume
├── chart/
│   ├── __init__.py
│   └── generator.py           # Matplotlib chart generation (timestamped + live PNGs)
├── charts/                    # Generated chart PNGs (gitignored)
├── setup_db.sql               # SQL DDL for initial table creation
├── requirements.txt           # Python dependencies
├── .env.example               # Template for environment variables
├── .gitignore
├── GETTING-STARTED.md         # Setup guide
└── FOR-Mohit-straddle-live-price.md  # Detailed project documentation
```

## Database Schema

PostgreSQL database: `straddle_db`

### straddle_sessions

| Column      | Type         | Description                               |
|-------------|--------------|-------------------------------------------|
| id          | SERIAL PK    | Auto-increment session ID                 |
| index_name  | VARCHAR(20)  | NIFTY or SENSEX                           |
| expiry_date | DATE         | Option expiry date                        |
| atm_strike  | DECIMAL(10,2)| ATM strike (updated dynamically)          |
| started_at  | TIMESTAMPTZ  | Session start (UTC)                       |
| ended_at    | TIMESTAMPTZ  | Session end (UTC), NULL if still running  |

### straddle_ticks

| Column         | Type         | Description                            |
|----------------|--------------|----------------------------------------|
| id             | SERIAL PK    | Auto-increment tick ID                 |
| session_id     | INTEGER FK   | References straddle_sessions.id        |
| timestamp      | TIMESTAMPTZ  | Tick time (UTC)                        |
| call_price     | DECIMAL(10,2)| Call option LTP                        |
| put_price      | DECIMAL(10,2)| Put option LTP                         |
| straddle_price | DECIMAL(10,2)| call_price + put_price                 |
| spot_price     | DECIMAL(10,2)| Index spot price (refreshed every 5s)  |

Indexes: `session_id`, `timestamp`

### straddle_charts

| Column       | Type         | Description                         |
|--------------|--------------|-------------------------------------|
| id           | SERIAL PK    | Auto-increment chart ID             |
| session_id   | INTEGER FK   | References straddle_sessions.id     |
| chart_path   | VARCHAR(500) | File path to chart PNG              |
| generated_at | TIMESTAMPTZ  | Generation time (UTC)               |

## Tech Stack

| Technology       | Purpose                                              |
|------------------|------------------------------------------------------|
| **kiteconnect**  | Official Zerodha SDK - API auth, instruments, ticker |
| **Playwright**   | Headless browser for automated Kite login + TOTP     |
| **pyotp**        | TOTP code generation for 2FA                         |
| **SQLAlchemy**   | ORM with connection pooling (QueuePool)              |
| **psycopg2**     | PostgreSQL adapter                                   |
| **matplotlib**   | Chart generation (seaborn-whitegrid style)           |
| **rich**         | Terminal UI with colored output and tables            |
| **python-dotenv**| Environment variable management                      |

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL
- Zerodha Kite Connect API credentials
- Playwright browsers (`playwright install chromium`)

### Installation

```bash
git clone https://github.com/mohitsharmadl/straddle-live-price.git
cd straddle-live-price

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Edit .env with your credentials
```

### Environment Variables

```env
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_USER_ID=your_user_id
KITE_PASSWORD=your_password
KITE_TOTP_SECRET=your_totp_secret    # Optional, for automated 2FA
HEADLESS_MODE=true                    # false for browser-based login
DATABASE_URL=postgresql://user:pass@localhost:5432/straddle_db
CHART_SAVE_INTERVAL=30               # Seconds between chart generations
CHARTS_DIR=./charts
```

### Database Setup

```bash
createdb straddle_db
psql -d straddle_db -f setup_db.sql
```

## Usage

### Headless Mode (default - for production/systemd)

```bash
python main.py
```

Automatically authenticates, picks the nearest expiry (0 DTE preferred), and starts tracking. Stops when market closes.

### Interactive Mode

```bash
python main.py --interactive
```

Prompts for index (NIFTY/SENSEX) and expiry date selection.

## Production Deployment

Runs as a **systemd service** (`straddle-tracker`) on the PROD server, managed by cron.

### Cron Jobs

| Schedule        | Script                 | Purpose                                   |
|-----------------|------------------------|-------------------------------------------|
| `* * * * *`     | `market-scheduler.sh`  | Start tracker at 9:15 AM, stop at 3:30 PM IST. Skips weekends and NSE holidays. |
| `30 3 * * 1-5`  | `kite_token_refresh.py`| Refresh Kite access token at 9:00 AM IST (UTC+5:30 = 3:30 UTC). Skips holidays. |

### NSE Holiday Calendar

Both `market-scheduler.sh` and `kite_token_refresh.py` include the 2026 NSE holiday calendar to avoid running on market holidays.

## Key Design Decisions

- **Tick batching**: Ticks are batched in groups of 10 before committing to PostgreSQL, reducing write overhead while keeping data loss minimal.
- **Session resume**: If the service restarts mid-day (e.g., systemd restart), it resumes the existing session rather than creating a duplicate.
- **Dynamic strike switching**: When the spot moves to a new ATM strike, the tracker stops the WebSocket, recalculates instruments, and restarts with a 2-second cooldown to let prices stabilize.
- **WebSocket staleness detection**: If no price updates arrive for 30 seconds, the ticker is automatically restarted with exponential backoff (up to 10 retries).
- **UTC storage, IST display**: All database timestamps are in UTC. IST conversion happens only at display time.
- **Cached spot price**: Spot price is fetched via REST every 5 seconds (not every tick) to avoid rate limits, while option prices stream via WebSocket.

## Useful Queries

```sql
-- Today's sessions
SELECT * FROM straddle_sessions
WHERE started_at::date = CURRENT_DATE
ORDER BY started_at DESC;

-- Latest 10 ticks
SELECT timestamp AT TIME ZONE 'Asia/Kolkata' AS ist_time,
       call_price, put_price, straddle_price, spot_price
FROM straddle_ticks
WHERE session_id = (SELECT MAX(id) FROM straddle_sessions)
ORDER BY timestamp DESC
LIMIT 10;

-- Intraday high/low/range
SELECT MIN(straddle_price) AS low,
       MAX(straddle_price) AS high,
       MAX(straddle_price) - MIN(straddle_price) AS range
FROM straddle_ticks
WHERE session_id = (SELECT MAX(id) FROM straddle_sessions);

-- Per-minute average
SELECT date_trunc('minute', timestamp) AS minute,
       ROUND(AVG(straddle_price), 2) AS avg_price
FROM straddle_ticks
WHERE session_id = (SELECT MAX(id) FROM straddle_sessions)
GROUP BY 1 ORDER BY 1;
```

## License

Private project. Not licensed for external use.
