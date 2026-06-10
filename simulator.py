import random
import time
import os
from datetime import datetime, timezone

import requests

from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL")

TOTAL_MESSAGES = 100

DEVICES = []

for i in range(1, 1001):
    if i <= 300:
        device_type = "boiler"
    elif i <= 700:
        device_type = "conveyor"
    else:
        device_type = "storage"

    DEVICES.append(
        {
            "device_id": f"{device_type}-{i:04d}",
            "device_type": device_type,
        }
    )


for i in range(TOTAL_MESSAGES):
    device = random.choice(DEVICES)

    payload = {}

    if device["device_type"] == "boiler":
        payload["temperature"] = random.randint(70, 130)
        payload["pressure"] = random.randint(150, 250)

    elif device["device_type"] == "conveyor":
        payload["rpm"] = random.randint(0, 700)

    elif device["device_type"] == "storage":
        payload["humidity"] = random.randint(50, 100)
        payload["temperature"] = random.randint(15, 40)

    telemetry = {
        "device_id": device["device_id"],
        "device_type": device["device_type"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    try:
        response = requests.post(
            API_URL,
            json=telemetry,
            timeout=5,
        )

        print(
            f"[{i + 1}/{TOTAL_MESSAGES}] "
            f"{device['device_id']} "
            f"({device['device_type']}) "
            f"-> {response.status_code}"
        )

    except Exception as e:
        print(
            f"[{i + 1}/{TOTAL_MESSAGES}] "
            f"{device['device_id']} "
            f"FAILED: {e}"
        )

    time.sleep(0.1)


print("\nSimulation complete.")
print(f"Logical devices created: {len(DEVICES)}")
print(f"Messages sent: {TOTAL_MESSAGES}")
