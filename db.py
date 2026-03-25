from sqlalchemy import create_engine, Column, Float, String, Integer, DateTime, desc
from sqlalchemy.orm import DeclarativeBase, Session
import os


class Base(DeclarativeBase):
    pass


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id = Column(Integer, primary_key=True)
    value = Column(Float)
    trend = Column(String)
    trend_raw = Column(Integer)
    sensor_timestamp = Column(String)
    recorded_at = Column(DateTime)


def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return create_engine(url)


def init_db(engine):
    Base.metadata.create_all(engine)


def insert_reading(session: Session, reading: dict) -> bool:
    exists = session.query(GlucoseReading).filter_by(
        sensor_timestamp=reading["timestamp"]
    ).first()
    if exists:
        return False
    from datetime import datetime, timezone
    session.add(GlucoseReading(
        value=reading["value"],
        trend=reading["trend"],
        trend_raw=reading["trend_raw"],
        sensor_timestamp=reading["timestamp"],
        recorded_at=datetime.now(timezone.utc),
    ))
    session.commit()
    return True


def get_latest(session: Session):
    return session.query(GlucoseReading).order_by(desc(GlucoseReading.recorded_at)).first()


def get_last_24h(session: Session):
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    parsed = func.to_timestamp(GlucoseReading.sensor_timestamp, 'MM/DD/YYYY HH12:MI:SS AM')
    return (
        session.query(GlucoseReading)
        .filter(parsed >= cutoff)
        .order_by(parsed)
        .all()
    )
