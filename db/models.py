"""
SQLAlchemy ORM models for straddle tracking.
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Date
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now():
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class StraddleSession(Base):
    """Represents one trading session (one morning run)."""
    __tablename__ = 'straddle_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_name = Column(String(20), nullable=False)  # 'NIFTY' or 'SENSEX'
    expiry_date = Column(Date, nullable=False)
    atm_strike = Column(Numeric(10, 2), nullable=False)
    started_at = Column(DateTime(timezone=True), default=utc_now)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    ticks = relationship('StraddleTick', back_populates='session', cascade='all, delete-orphan')
    charts = relationship('StraddleChart', back_populates='session', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<StraddleSession(id={self.id}, index={self.index_name}, strike={self.atm_strike})>"


class StraddleTick(Base):
    """Price tick recorded every second."""
    __tablename__ = 'straddle_ticks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('straddle_sessions.id'), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    call_price = Column(Numeric(10, 2), nullable=False)
    put_price = Column(Numeric(10, 2), nullable=False)
    straddle_price = Column(Numeric(10, 2), nullable=False)
    spot_price = Column(Numeric(10, 2), nullable=True)

    # Relationships
    session = relationship('StraddleSession', back_populates='ticks')

    def __repr__(self):
        return f"<StraddleTick(straddle={self.straddle_price}, time={self.timestamp})>"


class StraddleChart(Base):
    """Chart snapshot metadata."""
    __tablename__ = 'straddle_charts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('straddle_sessions.id'), nullable=False)
    chart_path = Column(String(500), nullable=True)
    generated_at = Column(DateTime(timezone=True), default=utc_now)

    # Relationships
    session = relationship('StraddleSession', back_populates='charts')

    def __repr__(self):
        return f"<StraddleChart(path={self.chart_path})>"
