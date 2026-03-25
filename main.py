from dotenv import load_dotenv
load_dotenv()

import asyncio
from datetime import datetime, timezone, timedelta
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from db import get_engine, init_db, get_latest, get_last_24h, insert_reading
from librelink import login, get_connections, get_graph, parse_reading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_token: str | None = None
_account_id: str | None = None


async def poll():
    global _token, _account_id
    try:
        if not _token:
            _token, _account_id = await login(
                os.getenv("LIBRE_EMAIL"), os.getenv("LIBRE_PASSWORD")
            )

        connections = await get_connections(_token, _account_id)
        if not connections:
            print("No connections found", flush=True)
            return

        connection = connections[0]
        patient_id = connection.get("patientId")
        if not patient_id:
            return

        graph_data = await get_graph(_token, _account_id, patient_id)
        raw_readings = graph_data.get("graphData", [])

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)

        engine = get_engine()
        with Session(engine) as session:
            new_count = 0
            for raw in raw_readings:
                reading = parse_reading(raw)
                try:
                    ts = datetime.strptime(reading["timestamp"], "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if ts > cutoff:
                    continue
                if insert_reading(session, reading):
                    new_count += 1

        print(f"[{datetime.now(timezone.utc).isoformat()}] +{new_count} new readings", flush=True)

    except Exception as e:
        print(f"Poll error: {e}", flush=True)
        _token = None
        _account_id = None


async def poll_loop():
    engine = get_engine()
    init_db(engine)
    print("Collector started, polling every 15 minutes...", flush=True)
    while True:
        await poll()
        await asyncio.sleep(900)


@app.on_event("startup")
async def startup():
    asyncio.create_task(poll_loop())


@app.get("/current")
def current():
    engine = get_engine()
    with Session(engine) as session:
        reading = get_latest(session)
        if not reading:
            raise HTTPException(status_code=503, detail="No data yet")
        return {
            "value": reading.value,
            "trend": reading.trend,
            "trend_raw": reading.trend_raw,
            "sensor_timestamp": reading.sensor_timestamp,
            "recorded_at": reading.recorded_at,
        }


@app.get("/readings")
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
