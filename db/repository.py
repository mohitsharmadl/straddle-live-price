"""
Data access layer for straddle tracking.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from .models import StraddleSession, StraddleTick, StraddleChart


class StraddleRepository:
    """Repository for straddle data operations."""

    def __init__(self, session: Session):
        self.session = session

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
            started_at=datetime.now()
        )
        self.session.add(straddle_session)
        self.session.commit()
        self.session.refresh(straddle_session)
        return straddle_session

    def end_session(self, session_id: int) -> Optional[StraddleSession]:
        """Mark a session as ended."""
        straddle_session = self.session.query(StraddleSession).get(session_id)
        if straddle_session:
            straddle_session.ended_at = datetime.now()
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

    # Tick operations
    def add_tick(
        self,
        session_id: int,
        call_price: Decimal,
        put_price: Decimal,
        spot_price: Optional[Decimal] = None,
        timestamp: Optional[datetime] = None
    ) -> StraddleTick:
        """Record a price tick."""
        straddle_price = call_price + put_price
        tick = StraddleTick(
            session_id=session_id,
            timestamp=timestamp or datetime.now(),
            call_price=call_price,
            put_price=put_price,
            straddle_price=straddle_price,
            spot_price=spot_price
        )
        self.session.add(tick)
        self.session.commit()
        self.session.refresh(tick)
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
        chart = StraddleChart(
            session_id=session_id,
            chart_path=chart_path,
            generated_at=datetime.now()
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
