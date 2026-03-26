import math

from sqlalchemy.orm import Session

from db import get_engine, get_readings_for_date, upsert_daily_stat


def calculate_daily_stats_for(date):
    engine = get_engine()
    with Session(engine) as session:
        rows = get_readings_for_date(session, date)
        if not rows:
            print(f"[daily] No readings for {date}", flush=True)
            return
        values = [r.value for r in rows]
        avg = sum(values) / len(values)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        sd = math.sqrt(variance)
        in_range = sum(1 for v in values if 4 <= v <= 9)
        tir = (in_range / len(values)) * 100
        avail = min((len(values) / 96) * 100, 100)
        upsert_daily_stat(session, date, round(tir), round(avg, 2), round(sd, 2), round(avail, 1))
        print(f"[daily] {date}: TIR={tir:.1f}% avg={avg:.2f} sd={sd:.2f} avail={avail:.1f}%", flush=True)


def daily_job():
    from datetime import date, timedelta
    yesterday = date.today() - timedelta(days=1)
    calculate_daily_stats_for(yesterday)
