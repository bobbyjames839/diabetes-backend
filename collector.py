import asyncio
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from db import get_engine, init_db, insert_reading
from librelink import login, get_connections, get_graph, parse_reading

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

        patient_id = connections[0].get("patientId")
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
