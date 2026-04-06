from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mobile_alerts import (
    get_mobile_alerts_enabled,
    get_mobile_alert_silence_until,
    get_mobile_alert_threshold_values,
    register_mobile_alert_device,
    set_mobile_alerts_enabled,
    set_mobile_alert_threshold_values,
    silence_mobile_alerts,
)
from mobile_libre import MOBILE_HIGH_THRESHOLD, MOBILE_LOW_THRESHOLD

router = APIRouter()


class RegisterAlertDeviceRequest(BaseModel):
    expo_push_token: str


class SilenceAlertRequest(BaseModel):
    expo_push_token: str
    minutes: int = 30


class AlertEnabledRequest(BaseModel):
    expo_push_token: str
    enabled: bool


class ThresholdRequest(BaseModel):
    expo_push_token: str
    low_threshold: float
    high_threshold: float


@router.post("/mobile/alerts/register")
def register_alert_device(body: RegisterAlertDeviceRequest):
    register_mobile_alert_device(body.expo_push_token)
    return {"ok": True}


@router.post("/mobile/alerts/silence")
def silence_alert(body: SilenceAlertRequest):
    silence_until = silence_mobile_alerts(body.expo_push_token, body.minutes)
    return {
        "ok": True,
        "silenced_until": silence_until.isoformat(),
    }


@router.post("/mobile/alerts/enabled")
def set_alert_enabled(body: AlertEnabledRequest):
    set_mobile_alerts_enabled(body.expo_push_token, body.enabled)
    return {"ok": True, "enabled": body.enabled}


@router.post("/mobile/alerts/thresholds")
def set_thresholds(body: ThresholdRequest):
    try:
        low_threshold, high_threshold = set_mobile_alert_threshold_values(
            body.expo_push_token,
            body.low_threshold,
            body.high_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "low_threshold": low_threshold,
        "high_threshold": high_threshold,
    }


@router.get("/mobile/alerts/status")
def alert_status(expo_push_token: str):
    silence_until = get_mobile_alert_silence_until(expo_push_token)
    alerts_enabled = get_mobile_alerts_enabled(expo_push_token)
    low_threshold, high_threshold = get_mobile_alert_threshold_values(
        expo_push_token,
        MOBILE_LOW_THRESHOLD,
        MOBILE_HIGH_THRESHOLD,
    )
    return {
        "silenced_until": silence_until.isoformat() if silence_until else None,
        "alerts_enabled": alerts_enabled,
        "low_threshold": low_threshold,
        "high_threshold": high_threshold,
    }
