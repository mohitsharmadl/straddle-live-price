"""
Data access layer for straddle tracking.
"""
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from .models import StraddleSession, StraddleTick, StraddleChart


def utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class StraddleRepository:
    """Repository for straddle data operations."""

    def __init__(self, session: Session):
        self.session = session
        self._pending_ticks: list[StraddleTick] = []
        self._batch_size = 10  # Commit every 10 ticks

    # Session operations
    def create_session(
        self,
        index_name: str,
        expiry_date: date,
        atm_strike: Decimal
    ) -> StraddleSession:
        """Create a new straddle tracking session."""
        straddle_session = StraddleSession(
            index_name=index_name,
            expiry_date=expiry_date,
            atm_strike=atm_strike,
            started_at=utc_now()
        )
        self.session.add(straddle_session)
        self.session.commit()
        self.session.refresh(straddle_session)
        return straddle_session

    def end_session(self, session_id: int) -> Optional[StraddleSession]:
        """Mark a session as ended."""
        # Flush any pending ticks before ending
        self._flush_pending_ticks()

        straddle_session = self.session.query(StraddleSession).get(session_id)
        if straddle_session:
            straddle_session.ended_at = utc_now()
            self.session.commit()
        return straddle_session

    def update_session_strike(self, session_id: int, new_strike: Decimal) -> Optional[StraddleSession]:
        """Update the ATM strike for a session (when spot moves)."""
        straddle_session = self.session.query(StraddleSession).get(session_id)
        if straddle_session:
            straddle_session.atm_strike = new_strike
            self.session.commit()
        return straddle_session

    def get_session(self, session_id: int) -> Optional[StraddleSession]:
        """Get a session by ID."""
        return self.session.query(StraddleSession).get(session_id)

    def get_active_sessions(self) -> list[StraddleSession]:
        """Get all sessions that haven't ended."""
        return self.session.query(StraddleSession).filter(
            StraddleSession.ended_at.is_(None)
        ).all()

    def _flush_pending_ticks(self):
        """Flush all pending ticks to the database."""
        if self._pending_ticks:
            self.session.add_all(self._pending_ticks)
            self.session.commit()
            self._pending_ticks = []

    # Tick operations
    def add_tick(
        self,
        session_id: int,
        call_price: Decimal,
        put_price: Decimal,
        spot_price: Optional[Decimal] = None,
        timestamp: Optional[datetime] = None
    ) -> StraddleTick:
        """
        Record a price tick with batching.

        Ticks are batched and committed every N ticks to reduce DB load.
        """
        straddle_price = call_price + put_price
        tick = StraddleTick(
            session_id=session_id,
            timestamp=timestamp or utc_now(),
            call_price=call_price,
            put_price=put_price,
            straddle_price=straddle_price,
            spot_price=spot_price
        )

        # Add to pending batch
        self._pending_ticks.append(tick)

        # Commit if batch is full
        if len(self._pending_ticks) >= self._batch_size:
            self._flush_pending_ticks()

        return tick

    def get_session_ticks(
        self,
        session_id: int,
        limit: Optional[int] = None
    ) -> list[StraddleTick]:
        """Get all ticks for a session, ordered by time."""
        query = self.session.query(StraddleTick).filter(
            StraddleTick.session_id == session_id
        ).order_by(StraddleTick.timestamp.asc())

        if limit:
            query = query.limit(limit)

        return query.all()

    def get_latest_tick(self, session_id: int) -> Optional[StraddleTick]:
        """Get the most recent tick for a session."""
        return self.session.query(StraddleTick).filter(
            StraddleTick.session_id == session_id
        ).order_by(StraddleTick.timestamp.desc()).first()

    def get_tick_count(self, session_id: int) -> int:
        """Get total number of ticks for a session."""
        return self.session.query(StraddleTick).filter(
            StraddleTick.session_id == session_id
        ).count()

    # Chart operations
    def add_chart(
        self,
        session_id: int,
        chart_path: str
    ) -> StraddleChart:
        """Record a chart snapshot."""
        # Flush pending ticks before adding chart
        self._flush_pending_ticks()

        chart = StraddleChart(
            session_id=session_id,
            chart_path=chart_path,
            generated_at=utc_now()
        )
        self.session.add(chart)
        self.session.commit()
        self.session.refresh(chart)
        return chart

    def get_session_charts(self, session_id: int) -> list[StraddleChart]:
        """Get all charts for a session."""
        return self.session.query(StraddleChart).filter(
            StraddleChart.session_id == session_id
        ).order_by(StraddleChart.generated_at.desc()).all()


    # Session resume operations
    def get_or_resume_session(
        self,
        index_name: str,
        expiry_date: date,
        atm_strike: Decimal
    ) -> tuple:
        """
        Get existing open session for today or create a new one.
        
        Returns: (session, is_resumed) tuple
        """
        from datetime import timezone, timedelta
        
        # IST timezone for date comparison
        IST = timezone(timedelta(hours=5, minutes=30))
        today_ist = datetime.now(IST).date()
        
        # Look for an open session (ended_at is NULL) that started today
        existing = self.session.query(StraddleSession).filter(
            StraddleSession.index_name == index_name,
            StraddleSession.ended_at.is_(None)
        ).order_by(StraddleSession.started_at.desc()).first()
        
        if existing:
            # Check if the session started today (in IST)
            session_date_ist = existing.started_at.astimezone(IST).date()
            if session_date_ist == today_ist:
                # Resume existing session, update strike if changed
                if existing.atm_strike != atm_strike:
                    existing.atm_strike = atm_strike
                    self.session.commit()
                print(f"[Resuming session {existing.id}]")
                return existing, True
        
        # Create new session
        new_session = self.create_session(index_name, expiry_date, atm_strike)
        return new_session, False
