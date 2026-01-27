# Straddle Live Price Tracker

## Daily Usage (Start Here!)

Run these commands every morning to start tracking:

```bash
cd /Users/mohitsharma/straddle-live-price
source venv/bin/activate
python main.py
```

**That's it!** The app will:
1. Open browser for Zerodha login (first time each day)
2. Let you select NIFTY or SENSEX
3. Let you pick expiry date
4. Start tracking straddle prices every second
5. Save charts to `charts/` folder every 30 seconds
6. Press `Ctrl+C` to stop

---

## One-Liner (Copy-Paste Daily)

```bash
cd /Users/mohitsharma/straddle-live-price && source venv/bin/activate && python main.py
```

---

## First-Time Setup (Already Done ✅)

<details>
<summary>Click to expand if you need to set up on a new machine</summary>

### Prerequisites
- Python 3.11+
- PostgreSQL installed and running
- Zerodha Kite API credentials

### Setup Commands

```bash
# Navigate to project
cd /Users/mohitsharma/straddle-live-price

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (copy and edit with your credentials)
cp .env.example .env

# Create database
createdb straddle_db
psql -d straddle_db -f setup_db.sql

# Run
python main.py
```

</details>

---

## Troubleshooting

### Database connection error
```bash
brew services start postgresql
```

### Kite authentication fails
- Check API key/secret in `.env`
- Ensure Kite subscription is active

### No instruments found
- Market might be closed (9:15 AM - 3:30 PM IST only)
- Check if selected index has active expiries
