import math
import re
from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from db import get_engine, get_last_24h, get_readings_for_date, get_all_daily_stats

router = APIRouter()

@router.get("/readings")
def readings():
    engine = get_engine()
    with Session(engine) as session:
        rows = get_last_24h(session)
        return [
            {
                "value": r.value,
                "trend": r.trend,
                "sensor_timestamp": r.sensor_timestamp,
            }
            for r in rows
        ]

@router.get("/readings/{date_str}")
def readings_for_date(date_str: str):
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise HTTPException(status_code=400, detail="Invalid date")
    engine = get_engine()
    with Session(engine) as session:
        d = date.fromisoformat(date_str)
        rows = get_readings_for_date(session, d)
        return [
            {
                "value": r.value,
                "trend": r.trend,
                "sensor_timestamp": r.sensor_timestamp,
            }
            for r in rows
        ]


@router.get("/daily-stats")
def daily_stats():
    engine = get_engine()
    with Session(engine) as session:
        rows = get_all_daily_stats(session)
        result = [
            {"date": r.date.isoformat(), "tir": r.tir, "avg": r.avg, "sd": r.sd, "avail": r.avail}
            for r in rows
        ]
        today = date.today()
        today_rows = get_readings_for_date(session, today)
        if today_rows:
            values = [r.value for r in today_rows]
            avg = sum(values) / len(values)
            variance = sum((v - avg) ** 2 for v in values) / len(values)
            sd = math.sqrt(variance)
            tir = (sum(1 for v in values if 4 <= v <= 9) / len(values)) * 100
            avail = min((len(values) / 96) * 100, 100)
            today_entry = {
                "date": today.isoformat(),
                "tir": round(tir),
                "avg": round(avg, 2),
                "sd": round(sd, 2),
                "avail": round(avail, 1),
            }
            result = [r for r in result if r["date"] != today.isoformat()]
            result.append(today_entry)
        return result
