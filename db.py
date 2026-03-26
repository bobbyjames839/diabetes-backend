from sqlalchemy import create_engine, Column, Float, String, Integer, DateTime, Date, desc
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


class DailyStat(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    tir = Column(Float)
    avg = Column(Float)
    sd = Column(Float)
    avail = Column(Float)


def upsert_daily_stat(session: Session, date, tir: float, avg: float, sd: float, avail: float):
    existing = session.query(DailyStat).filter_by(date=date).first()
    if existing:
        existing.tir = tir
        existing.avg = avg
        existing.sd = sd
        existing.avail = avail
    else:
        session.add(DailyStat(date=date, tir=tir, avg=avg, sd=sd, avail=avail))
    session.commit()


def get_all_daily_stats(session: Session):
    return session.query(DailyStat).order_by(DailyStat.date).all()


def get_readings_for_date(session: Session, date):
    from datetime import datetime
    date_str = date.strftime("%-m/%-d/%Y")
    rows = session.query(GlucoseReading).filter(
        GlucoseReading.sensor_timestamp.like(f"{date_str} %")
    ).all()
    return rows


def get_daily_stats_range(session: Session, start_date, end_date):
    return (
        session.query(DailyStat)
        .filter(DailyStat.date >= start_date, DailyStat.date <= end_date)
        .order_by(DailyStat.date)
        .all()
    )


def get_readings_range(session: Session, start_date, end_date):
    from sqlalchemy import func
    from datetime import datetime, timezone
    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    parsed = func.to_timestamp(GlucoseReading.sensor_timestamp, 'MM/DD/YYYY HH12:MI:SS AM')
    return (
        session.query(GlucoseReading)
        .filter(parsed >= start_dt, parsed <= end_dt)
        .order_by(parsed)
        .all()
    )


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
