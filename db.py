from sqlalchemy import Boolean, create_engine, Column, Float, String, Integer, DateTime, Date, Text
from sqlalchemy.orm import DeclarativeBase, Session
import os
from datetime import datetime, timezone


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


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        _engine = create_engine(url, pool_size=2, max_overflow=2)
    return _engine


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


class RawInput(Base):
    __tablename__ = "raw_inputs"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    source = Column(String)  # 'text' or 'voice'
    created_at = Column(DateTime)


def save_raw_input(session: Session, content: str, source: str):
    from datetime import datetime, timezone
    entry = RawInput(
        content=content,
        source=source,
        created_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_raw_inputs(session: Session, limit: int = 200):
    rows = (
        session.query(RawInput)
        .order_by(RawInput.created_at.desc(), RawInput.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def delete_raw_input(session: Session, entry_id: int) -> bool:
    entry = session.get(RawInput, entry_id)
    if entry is None:
        return False

    session.delete(entry)
    session.commit()
    return True


class MobileAlertDevice(Base):
    __tablename__ = "mobile_alert_devices"

    id = Column(Integer, primary_key=True)
    expo_push_token = Column(String, unique=True, nullable=False)
    silence_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


class MobileAlertPreference(Base):
    __tablename__ = "mobile_alert_preferences"

    id = Column(Integer, primary_key=True)
    expo_push_token = Column(String, unique=True, nullable=False)
    alerts_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


class MobileAlertThreshold(Base):
    __tablename__ = "mobile_alert_thresholds"

    id = Column(Integer, primary_key=True)
    expo_push_token = Column(String, unique=True, nullable=False)
    low_threshold = Column(Float, nullable=False)
    high_threshold = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


def upsert_mobile_alert_device(session: Session, expo_push_token: str):
    device = (
        session.query(MobileAlertDevice)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    now = datetime.now(timezone.utc)

    if device:
        device.updated_at = now
    else:
        device = MobileAlertDevice(
            expo_push_token=expo_push_token,
            created_at=now,
            updated_at=now,
        )
        session.add(device)

    session.commit()
    return device


def remove_mobile_alert_device(session: Session, expo_push_token: str) -> bool:
    device = (
        session.query(MobileAlertDevice)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    if device is None:
        return False

    session.delete(device)
    session.commit()
    return True


def set_mobile_alert_silence(session: Session, expo_push_token: str, silence_until):
    device = (
        session.query(MobileAlertDevice)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    if device is None:
        device = MobileAlertDevice(
            expo_push_token=expo_push_token,
            created_at=datetime.now(timezone.utc),
        )
        session.add(device)

    device.silence_until = silence_until
    device.updated_at = datetime.now(timezone.utc)
    session.commit()


def get_mobile_alert_silence(session: Session, expo_push_token: str):
    device = (
        session.query(MobileAlertDevice)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    return device.silence_until if device else None


def set_mobile_alert_enabled(session: Session, expo_push_token: str, enabled: bool):
    preference = (
        session.query(MobileAlertPreference)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    now = datetime.now(timezone.utc)

    if preference is None:
        preference = MobileAlertPreference(
            expo_push_token=expo_push_token,
            alerts_enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        session.add(preference)
    else:
        preference.alerts_enabled = enabled
        preference.updated_at = now

    session.commit()


def get_mobile_alert_enabled(session: Session, expo_push_token: str) -> bool:
    preference = (
        session.query(MobileAlertPreference)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    if preference is None:
        return True
    return bool(preference.alerts_enabled)


def set_mobile_alert_thresholds(
    session: Session,
    expo_push_token: str,
    low_threshold: float,
    high_threshold: float,
):
    row = (
        session.query(MobileAlertThreshold)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    now = datetime.now(timezone.utc)

    if row is None:
        row = MobileAlertThreshold(
            expo_push_token=expo_push_token,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.low_threshold = low_threshold
        row.high_threshold = high_threshold
        row.updated_at = now

    session.commit()


def get_mobile_alert_thresholds(
    session: Session,
    expo_push_token: str,
    default_low_threshold: float,
    default_high_threshold: float,
):
    row = (
        session.query(MobileAlertThreshold)
        .filter_by(expo_push_token=expo_push_token)
        .first()
    )
    if row is None:
        return default_low_threshold, default_high_threshold
    return float(row.low_threshold), float(row.high_threshold)


def get_mobile_alert_target_configs(
    session: Session,
    now,
    default_low_threshold: float,
    default_high_threshold: float,
):
    device_rows = session.query(MobileAlertDevice).all()
    preference_rows = session.query(MobileAlertPreference).all()
    threshold_rows = session.query(MobileAlertThreshold).all()

    enabled_by_token = {
        row.expo_push_token: bool(row.alerts_enabled)
        for row in preference_rows
        if row.expo_push_token
    }
    thresholds_by_token = {
        row.expo_push_token: (float(row.low_threshold), float(row.high_threshold))
        for row in threshold_rows
        if row.expo_push_token
    }

    result = []
    for device in device_rows:
        token = device.expo_push_token
        if not token:
            continue
        if not enabled_by_token.get(token, True):
            continue
        if device.silence_until is not None and device.silence_until > now:
            continue

        low_threshold, high_threshold = thresholds_by_token.get(
            token,
            (default_low_threshold, default_high_threshold),
        )
        result.append(
            {
                "expo_push_token": token,
                "low_threshold": low_threshold,
                "high_threshold": high_threshold,
            }
        )

    return result


def get_mobile_alert_targets(session: Session, now):
    configs = get_mobile_alert_target_configs(
        session,
        now,
        default_low_threshold=4.0,
        default_high_threshold=10.0,
    )
    return [config["expo_push_token"] for config in configs]
