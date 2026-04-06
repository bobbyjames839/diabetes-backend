import asyncio
import copy
import os
from datetime import datetime, timezone
from typing import Any

from librelink import get_connections, get_graph, login, parse_reading
from mobile_alerts import dispatch_threshold_alerts

MOBILE_LOW_THRESHOLD = float(os.getenv("MOBILE_LOW_THRESHOLD", "4"))
MOBILE_HIGH_THRESHOLD = float(os.getenv("MOBILE_HIGH_THRESHOLD", "10"))

_token: str | None = None
_account_id: str | None = None
_state_lock = asyncio.Lock()
_latest_payload: dict[str, Any] = {
    "reading": None,
    "status": "unknown",
    "updated_at": None,
    "error": None,
    "low_threshold": MOBILE_LOW_THRESHOLD,
    "high_threshold": MOBILE_HIGH_THRESHOLD,
}


def _parse_sensor_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _classify_value(value: Any) -> str:
    return classify_value(value, MOBILE_LOW_THRESHOLD, MOBILE_HIGH_THRESHOLD)


def classify_value(value: Any, low_threshold: float, high_threshold: float) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    if value < low_threshold:
        return "low"
    if value > high_threshold:
        return "high"
    return "in_range"


async def _fetch_latest_reading() -> dict[str, Any]:
    global _token, _account_id

    if not _token:
        _token, _account_id = await login(
            os.getenv("LIBRE_EMAIL"), os.getenv("LIBRE_PASSWORD")
        )

    connections = await get_connections(_token, _account_id)
    if not connections:
        raise RuntimeError("No Libre connections found")

    patient_id = connections[0].get("patientId")
    if not patient_id:
        raise RuntimeError("Libre connection missing patient id")

    graph_data = await get_graph(_token, _account_id, patient_id)
    raw_readings = graph_data.get("graphData", [])
    if not raw_readings:
        raise RuntimeError("No Libre graph readings returned")

    latest_reading: dict[str, Any] | None = None
    latest_timestamp: datetime | None = None

    for raw in raw_readings:
        reading = parse_reading(raw)
        ts = _parse_sensor_timestamp(reading.get("timestamp"))
        if ts is None:
            continue
        if latest_timestamp is None or ts > latest_timestamp:
            latest_timestamp = ts
            latest_reading = reading

    if latest_reading is None:
        raise RuntimeError("Could not parse Libre reading timestamps")

    return latest_reading


async def poll_mobile_once() -> None:
    global _token, _account_id

    try:
        reading = await _fetch_latest_reading()
        status = _classify_value(reading.get("value"))

        async with _state_lock:
            _latest_payload["reading"] = reading
            _latest_payload["status"] = status
            _latest_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            _latest_payload["error"] = None

        # Send a push alert for every high/low poll unless silenced by device settings.
        await dispatch_threshold_alerts(
            reading,
            default_low_threshold=MOBILE_LOW_THRESHOLD,
            default_high_threshold=MOBILE_HIGH_THRESHOLD,
        )

    except Exception as exc:
        _token = None
        _account_id = None
        async with _state_lock:
            _latest_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            _latest_payload["error"] = str(exc)
        print(f"[mobile_libre] Poll error: {exc}", flush=True)


async def mobile_poll_loop() -> None:
    print("Mobile Libre poller started (every 5 minutes)", flush=True)
    while True:
        await poll_mobile_once()
        await asyncio.sleep(300)


async def get_latest_mobile_payload() -> dict[str, Any]:
    async with _state_lock:
        return copy.deepcopy(_latest_payload)
