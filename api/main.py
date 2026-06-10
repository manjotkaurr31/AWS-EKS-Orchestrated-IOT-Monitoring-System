from datetime import datetime
from typing import Dict, Any
import os
import boto3
from fastapi import FastAPI, status
from pydantic import BaseModel

from dotenv import load_dotenv

load_dotenv()

QUEUE_URL = os.getenv("QUEUE_URL")

sqs = boto3.client(
    "sqs",
    region_name=os.getenv("AWS_REGION")
)


class TelemetryRequest(BaseModel):
    device_id: str
    device_type: str
    recorded_at: datetime
    payload: Dict[str, Any]


app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/telemetry", status_code=status.HTTP_202_ACCEPTED)
def ingest_telemetry(request: TelemetryRequest):

    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=request.model_dump_json()
    )

    return {
        "message": "Telemetry accepted",
        "message_id": response["MessageId"]
    }
