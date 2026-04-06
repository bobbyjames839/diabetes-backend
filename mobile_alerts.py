from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from db import (
    get_engine,
    get_mobile_alert_enabled,
    get_mobile_alert_silence,
    get_mobile_alert_target_configs,
    get_mobile_alert_thresholds,
    remove_mobile_alert_device,
    set_mobile_alert_enabled,
    set_mobile_alert_silence,
    set_mobile_alert_thresholds,
    upsert_mobile_alert_device,
)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def register_mobile_alert_device(expo_push_token: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        upsert_mobile_alert_device(session, expo_push_token)


def unregister_mobile_alert_device(expo_push_token: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        remove_mobile_alert_device(session, expo_push_token)


def silence_mobile_alerts(expo_push_token: str, minutes: int) -> datetime:
    clamped_minutes = max(1, min(minutes, 720))
    silence_until = datetime.now(timezone.utc) + timedelta(minutes=clamped_minutes)
    engine = get_engine()
    with Session(engine) as session:
        upsert_mobile_alert_device(session, expo_push_token)
        set_mobile_alert_silence(session, expo_push_token, silence_until)
    return silence_until


def get_mobile_alert_silence_until(expo_push_token: str) -> datetime | None:
    engine = get_engine()
    with Session(engine) as session:
        return get_mobile_alert_silence(session, expo_push_token)


def set_mobile_alerts_enabled(expo_push_token: str, enabled: bool) -> None:
    engine = get_engine()
    with Session(engine) as session:
        upsert_mobile_alert_device(session, expo_push_token)
        set_mobile_alert_enabled(session, expo_push_token, enabled)


def get_mobile_alerts_enabled(expo_push_token: str) -> bool:
    engine = get_engine()
    with Session(engine) as session:
        return get_mobile_alert_enabled(session, expo_push_token)


def set_mobile_alert_threshold_values(
    expo_push_token: str,
    low_threshold: float,
    high_threshold: float,
) -> tuple[float, float]:
    if low_threshold <= 0:
        raise ValueError("Low threshold must be greater than 0")
    if high_threshold <= low_threshold:
        raise ValueError("High threshold must be greater than low threshold")

    engine = get_engine()
    with Session(engine) as session:
        upsert_mobile_alert_device(session, expo_push_token)
        set_mobile_alert_thresholds(
            session,
            expo_push_token,
            float(low_threshold),
            float(high_threshold),
        )

    return float(low_threshold), float(high_threshold)


def get_mobile_alert_threshold_values(
    expo_push_token: str,
    default_low_threshold: float,
    default_high_threshold: float,
) -> tuple[float, float]:
    engine = get_engine()
    with Session(engine) as session:
        return get_mobile_alert_thresholds(
            session,
            expo_push_token,
            default_low_threshold,
            default_high_threshold,
        )


def _classify_value(value: Any, low_threshold: float, high_threshold: float) -> str:
    if not isinstance(value, (float, int)):
        return "unknown"
    if value < low_threshold:
        return "low"
    if value > high_threshold:
        return "high"
    return "in_range"


async def _send_expo_push(messages: list[dict[str, Any]]) -> None:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(EXPO_PUSH_URL, json=messages)
        response.raise_for_status()
        response_json = response.json()

    data = response_json.get("data", []) if isinstance(response_json, dict) else []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        if item.get("status") != "error":
            continue

        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        if details.get("error") != "DeviceNotRegistered":
            continue

        # Remove invalid tokens so repeated sends don't keep failing.
        token = messages[index].get("to") if index < len(messages) else None
        if isinstance(token, str) and token:
            unregister_mobile_alert_device(token)


async def dispatch_threshold_alerts(
    reading: dict[str, Any],
    default_low_threshold: float,
    default_high_threshold: float,
) -> None:
    value = reading.get("value")
    if not isinstance(value, (float, int)):
        return

    trend = reading.get("trend") or ""
    value_text = f"{value:.1f}" if isinstance(value, (float, int)) else "Unknown"

    now = datetime.now(timezone.utc)
    engine = get_engine()
    with Session(engine) as session:
        target_configs = get_mobile_alert_target_configs(
            session,
            now,
            default_low_threshold,
            default_high_threshold,
        )

    if not target_configs:
        return

    messages: list[dict[str, Any]] = []
    for config in target_configs:
        token = config.get("expo_push_token")
        low_threshold = float(config.get("low_threshold", default_low_threshold))
        high_threshold = float(config.get("high_threshold", default_high_threshold))
        status = _classify_value(value, low_threshold, high_threshold)
        if status not in {"low", "high"}:
            continue

        body = (
            f"LOW glucose: {value_text} mmol/L {trend}" if status == "low"
            else f"HIGH glucose: {value_text} mmol/L {trend}"
        )
        messages.append(
            {
                "to": token,
                "title": "Glucose Alert",
                "body": body,
                "data": {
                    "status": status,
                    "value": value,
                    "trend": trend,
                    "timestamp": reading.get("timestamp"),
                    "low_threshold": low_threshold,
                    "high_threshold": high_threshold,
                },
                "sound": "default",
                "priority": "high",
                "channelId": "glucose-alerts",
            }
        )

    if not messages:
        return

    try:
        await _send_expo_push(messages)
    except Exception as exc:
        print(f"[mobile_alerts] Push send error: {exc}", flush=True)
