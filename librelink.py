import httpx
import os
import hashlib

TREND_ARROWS = {
    1: "↓↓",
    2: "↓",
    3: "→",
    4: "↑",
    5: "↑↑",
}

BASE_HEADERS = {
    "version": "4.16.0",
    "product": "llu.ios",
    "Content-Type": "application/json",
    "User-Agent": "FreeStyle LibreLink 4.16.0",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _url(path: str) -> str:
    base = os.getenv("LIBRE_URL", "https://api-us.libreview.io")
    return f"{base}{path}"


async def login(email: str, password: str) -> tuple[str, str]:
    """Returns (token, account_id)"""
    async with httpx.AsyncClient() as client:
        url = _url("/llu/auth/login")
        response = await client.post(
            url,
            json={"email": email, "password": password},
            headers=BASE_HEADERS,
        )
        response.raise_for_status()
        data = response.json()

        # Follow region redirect if needed
        if data.get("data", {}).get("redirect"):
            region = data["data"]["region"]
            new_base = f"https://api-{region}.libreview.io"
            os.environ["LIBRE_URL"] = new_base
            print(f"Redirecting to region: {region}")
            response = await client.post(
                f"{new_base}/llu/auth/login",
                json={"email": email, "password": password},
                headers=BASE_HEADERS,
            )
            response.raise_for_status()
            data = response.json()

        token = data["data"]["authTicket"]["token"]
        account_id = data["data"]["user"]["id"]
        return token, account_id


async def get_connections(token: str, account_id: str) -> list:
    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token}",
        "account-id": hashlib.sha256(account_id.encode()).hexdigest(),
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(_url("/llu/connections"), headers=headers)
        print(f"Connections response ({response.status_code}): {response.text}")
        response.raise_for_status()
        return response.json().get("data", [])


async def get_graph(token: str, account_id: str, patient_id: str) -> dict:
    headers = {
        **BASE_HEADERS,
        "Authorization": f"Bearer {token}",
        "account-id": hashlib.sha256(account_id.encode()).hexdigest(),
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(
            _url(f"/llu/connections/{patient_id}/graph"), headers=headers
        )
        response.raise_for_status()
        return response.json().get("data", {})


def parse_reading(glucose_measurement: dict) -> dict:
    trend_raw = glucose_measurement.get("TrendArrow", 3)
    return {
        "value": glucose_measurement.get("Value"),
        "trend": TREND_ARROWS.get(trend_raw, "→"),
        "trend_raw": trend_raw,
        "timestamp": glucose_measurement.get("Timestamp"),
    }
