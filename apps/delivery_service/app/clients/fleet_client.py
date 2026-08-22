import os

import httpx
from httpx import TimeoutException

FLEET_SERVICE_URL = os.environ.get("FLEET_SERVICE_URL", "http://127.0.0.1:8001")


async def assign_truck_to_delivery(delivery_id: str, cargo_weight_kg: int) -> str | None:
    async with httpx.AsyncClient() as client:
        url = f"{FLEET_SERVICE_URL}/internal/truck-assignments"
        payload = {"delivery_id": delivery_id, "cargo_weight_kg": cargo_weight_kg}
        response = await client.post(url, json=payload)
        response_json = response.json()

        if response.status_code == 422:
            raise Exception(f"{response_json['detail']}")

        if response.status_code == 200:
            if response_json["assigned"] is False:
                # TODO : Log response_json["reason"]
                return None

            return response_json["truck_id"]

    raise TimeoutException("Failed to assign truck to delivery.")