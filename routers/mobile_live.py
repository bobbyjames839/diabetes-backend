from fastapi import APIRouter

from mobile_libre import (
    get_latest_mobile_payload,
)

router = APIRouter()


@router.get("/mobile/live-reading")
async def mobile_live_reading():
    payload = await get_latest_mobile_payload()

    # Live mobile data is sourced from LibreLinkUp state only.
    payload["silenced_until"] = None
    payload["alerts_enabled"] = True

    return payload
