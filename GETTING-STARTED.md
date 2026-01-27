# Getting Started - Straddle Live Price Tracker

## Prerequisites

- Python 3.11+
- PostgreSQL installed and running
- Zerodha Kite API credentials (get from [Kite Connect](https://developers.kite.trade/))

---

## Setup Commands

### 1. Navigate to project

```bash
cd /Users/mohitsharma/straddle-live-price
```

### 2. Create virtual environment

```bash
python -m venv venv
```

### 3. Activate virtual environment

```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure environment

```bash
cp .env.example .env
```

Then edit `.env` with your credentials:
```
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
DATABASE_URL=postgresql://username:password@localhost:5432/straddle_db
```

### 6. Create PostgreSQL database

```bash
createdb straddle_db
```

### 7. Create database tables

```bash
psql -d straddle_db -f setup_db.sql
```

### 8. Run the application

```bash
python main.py
```

---

## Quick Start (Copy-Paste)

```bash
cd /Users/mohitsharma/straddle-live-price
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
createdb straddle_db
psql -d straddle_db -f setup_db.sql
python main.py
```

---

## Daily Usage

```bash
cd /Users/mohitsharma/straddle-live-price
source venv/bin/activate
python main.py
```

---

## What Happens When You Run

1. App authenticates with Zerodha (opens browser first time each day)
2. Select index: NIFTY or SENSEX
3. Select expiry date
4. Press Enter to start tracking
5. Watch live straddle prices every second
6. Charts auto-generated every 30 seconds in `charts/` folder
7. Press `Ctrl+C` to stop

---

## Troubleshooting

### Database connection error
Make sure PostgreSQL is running:
```bash
brew services start postgresql
```

### Kite authentication fails
- Check your API key/secret in `.env`
- Ensure your Kite subscription is active

### No instruments found
- Market might be closed
- Check if the selected index has active expiries
