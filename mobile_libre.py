import asyncio
import copy
import os
from datetime import datetime, timezone
from typing import Any

from librelink import get_connections, get_graph, login, parse_reading
from mobile_alerts import dispatch_threshold_alerts

MOBILE_LOW_THRESHOLD = float(os.getenv("MOBILE_LOW_THRESHOLD", "4"))
MOBILE_HIGH_THRESHOLD = float(os.getenv("MOBILE_HIGH_THRESHOLD", "10"))
MOBILE_BACKGROUND_POLL_INTERVAL_SECONDS = max(
    20,
    int(os.getenv("MOBILE_BACKGROUND_POLL_INTERVAL_SECONDS", "60")),
)

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


def _extract_connection_reading(connection: dict[str, Any]) -> tuple[str, dict[str, Any], datetime] | None:
    patient_id = connection.get("patientId")
    glucose_measurement = connection.get("glucoseMeasurement")
    if not patient_id or not isinstance(glucose_measurement, dict):
        return None

    reading = parse_reading(glucose_measurement)
    ts = _parse_sensor_timestamp(reading.get("timestamp"))
    if ts is None:
        return None

    return patient_id, reading, ts


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

    latest_patient_id: str | None = None
    latest_connection_reading: dict[str, Any] | None = None
    latest_connection_timestamp: datetime | None = None

    for connection in connections:
        extracted = _extract_connection_reading(connection)
        if extracted is None:
            continue

        patient_id, reading, ts = extracted
        if latest_connection_timestamp is None or ts > latest_connection_timestamp:
            latest_patient_id = patient_id
            latest_connection_reading = reading
            latest_connection_timestamp = ts

    if latest_patient_id is None:
        latest_patient_id = connections[0].get("patientId")

    if not latest_patient_id:
        raise RuntimeError("Libre connection missing patient id")

    graph_data = await get_graph(_token, _account_id, latest_patient_id)
    raw_readings = graph_data.get("graphData", [])

    latest_graph_reading: dict[str, Any] | None = None
    latest_graph_timestamp: datetime | None = None

    for raw in raw_readings:
        reading = parse_reading(raw)
        ts = _parse_sensor_timestamp(reading.get("timestamp"))
        if ts is None:
            continue
        if latest_graph_timestamp is None or ts > latest_graph_timestamp:
            latest_graph_timestamp = ts
            latest_graph_reading = reading

    if latest_graph_reading is not None and (
        latest_connection_timestamp is None or latest_graph_timestamp is None or latest_graph_timestamp >= latest_connection_timestamp
    ):
        return latest_graph_reading

    if latest_connection_reading is not None:
        return latest_connection_reading

    raise RuntimeError("Could not parse Libre reading timestamps")


async def refresh_mobile_payload(dispatch_alerts: bool = True) -> dict[str, Any]:
    global _token, _account_id

    try:
        reading = await _fetch_latest_reading()
        status = _classify_value(reading.get("value"))

        async with _state_lock:
            _latest_payload["reading"] = reading
            _latest_payload["status"] = status
            _latest_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            _latest_payload["error"] = None
            payload = copy.deepcopy(_latest_payload)

        if dispatch_alerts:
            # Send a push alert for every high/low poll unless silenced by device settings.
            await dispatch_threshold_alerts(
                reading,
                default_low_threshold=MOBILE_LOW_THRESHOLD,
                default_high_threshold=MOBILE_HIGH_THRESHOLD,
            )

        return payload

    except Exception as exc:
        _token = None
        _account_id = None
        async with _state_lock:
            _latest_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            _latest_payload["error"] = str(exc)
            payload = copy.deepcopy(_latest_payload)
        print(f"[mobile_libre] Poll error: {exc}", flush=True)
        return payload


async def poll_mobile_once() -> None:
    await refresh_mobile_payload(dispatch_alerts=True)


async def mobile_poll_loop() -> None:
    print(
        f"Mobile Libre poller started (every {MOBILE_BACKGROUND_POLL_INTERVAL_SECONDS} seconds)",
        flush=True,
    )
    while True:
        await poll_mobile_once()
        await asyncio.sleep(MOBILE_BACKGROUND_POLL_INTERVAL_SECONDS)


async def get_latest_mobile_payload(
    force_refresh: bool = False,
    dispatch_alerts: bool = False,
) -> dict[str, Any]:
    if force_refresh:
        return await refresh_mobile_payload(dispatch_alerts=dispatch_alerts)

    async with _state_lock:
        return copy.deepcopy(_latest_payload)
