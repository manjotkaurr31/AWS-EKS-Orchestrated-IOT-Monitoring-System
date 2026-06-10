import json
import os
import time
import uuid

import boto3
from sqlalchemy import create_engine, text

from dotenv import load_dotenv

load_dotenv()

QUEUE_URL = os.getenv("QUEUE_URL")

DB_HOST = os.getenv("DB_HOST")
DB_PORT = 5432
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

THRESHOLDS = {
    "temperature": 100,
    "humidity": 90,
    "high_rpm": 500,
    "low_rpm": 50,
    "pressure": 200,
}


sqs = boto3.client(
    "sqs",
    region_name=os.getenv("AWS_REGION")
)

cloudwatch = boto3.client(
    "cloudwatch",
    region_name=os.getenv("AWS_REGION")
)

engine = create_engine(
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


def publish_metric(metric_name: str):
    cloudwatch.put_metric_data(
        Namespace="FactoryMonitoring",
        MetricData=[
            {
                "MetricName": metric_name,
                "Value": 1,
                "Unit": "Count",
            }
        ],
    )


def store_telemetry(message: dict):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO telemetry (
                    id,
                    device_id,
                    device_type,
                    recorded_at,
                    payload
                )
                VALUES (
                    :id,
                    :device_id,
                    :device_type,
                    :recorded_at,
                    CAST(:payload AS JSONB)
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "device_id": message["device_id"],
                "device_type": message["device_type"],
                "recorded_at": message["recorded_at"],
                "payload": json.dumps(message["payload"]),
            },
        )


def evaluate_thresholds(payload: dict):
    if payload.get("temperature", 0) > THRESHOLDS["temperature"]:
        publish_metric("HighTemperature")

    if payload.get("humidity", 0) > THRESHOLDS["humidity"]:
        publish_metric("HighHumidity")

    if payload.get("pressure", 0) > THRESHOLDS["pressure"]:
        publish_metric("HighPressure")

    if payload.get("rpm", 0) > THRESHOLDS["high_rpm"]:
        publish_metric("HighRPM")

    if (
        "rpm" in payload
        and payload["rpm"] < THRESHOLDS["low_rpm"]
    ):
        publish_metric("LowRPM")


print("Worker started...")


while True:
    response = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
    )

    messages = response.get("Messages", [])

    if not messages:
        continue

    for message in messages:
        receipt_handle = message["ReceiptHandle"]

        try:
            body = json.loads(message["Body"])

            store_telemetry(body)

            evaluate_thresholds(body["payload"])

            sqs.delete_message(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=receipt_handle,
            )

            print(
                f"Processed message for device "
                f"{body['device_id']}"
            )

        except Exception as e:
            print(f"Error processing message: {e}")

    time.sleep(1)
	
