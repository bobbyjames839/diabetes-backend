from fastapi import APIRouter
from sqlalchemy.orm import Session

from db import (
    get_engine,
    get_mobile_alert_enabled,
    get_mobile_alert_silence,
    get_mobile_alert_thresholds,
)
from mobile_libre import (
    MOBILE_HIGH_THRESHOLD,
    MOBILE_LOW_THRESHOLD,
    classify_value,
    get_latest_mobile_payload,
)

router = APIRouter()


@router.get("/mobile/live-reading")
async def mobile_live_reading(expo_push_token: str | None = None):
    payload = await get_latest_mobile_payload()

    if expo_push_token:
        engine = get_engine()
        with Session(engine) as session:
            silence_until = get_mobile_alert_silence(session, expo_push_token)
            alerts_enabled = get_mobile_alert_enabled(session, expo_push_token)
            low_threshold, high_threshold = get_mobile_alert_thresholds(
                session,
                expo_push_token,
                MOBILE_LOW_THRESHOLD,
                MOBILE_HIGH_THRESHOLD,
            )
        payload["silenced_until"] = silence_until.isoformat() if silence_until else None
        payload["alerts_enabled"] = alerts_enabled
        payload["low_threshold"] = low_threshold
        payload["high_threshold"] = high_threshold
        reading_value = payload.get("reading", {}).get("value") if payload.get("reading") else None
        payload["status"] = classify_value(reading_value, low_threshold, high_threshold)
    else:
        payload["silenced_until"] = None
        payload["alerts_enabled"] = True

    return payload
