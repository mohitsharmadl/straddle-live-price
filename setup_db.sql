-- Straddle Live Price - Database Setup
-- Run this script to create the required tables in PostgreSQL
-- Usage: psql -U username -d straddle_db -f setup_db.sql

-- Create database (run separately as superuser if needed)
-- CREATE DATABASE straddle_db;

-- Sessions table (one per morning run)
CREATE TABLE IF NOT EXISTS straddle_sessions (
    id SERIAL PRIMARY KEY,
    index_name VARCHAR(20) NOT NULL,  -- 'NIFTY' or 'SENSEX'
    expiry_date DATE NOT NULL,
    atm_strike DECIMAL(10,2) NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP
);

-- Price ticks (one per second)
CREATE TABLE IF NOT EXISTS straddle_ticks (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES straddle_sessions(id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL,
    call_price DECIMAL(10,2) NOT NULL,
    put_price DECIMAL(10,2) NOT NULL,
    straddle_price DECIMAL(10,2) NOT NULL,
    spot_price DECIMAL(10,2)
);

-- Chart snapshots
CREATE TABLE IF NOT EXISTS straddle_charts (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES straddle_sessions(id) ON DELETE CASCADE,
    chart_path VARCHAR(500),
    generated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_ticks_session_id ON straddle_ticks(session_id);
CREATE INDEX IF NOT EXISTS idx_ticks_timestamp ON straddle_ticks(timestamp);
CREATE INDEX IF NOT EXISTS idx_charts_session_id ON straddle_charts(session_id);

-- Grant permissions (adjust username as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_user;

COMMENT ON TABLE straddle_sessions IS 'Tracks individual tracking sessions (one per morning run)';
COMMENT ON TABLE straddle_ticks IS 'Stores price data every second during a session';
COMMENT ON TABLE straddle_charts IS 'Stores paths to generated chart images';
