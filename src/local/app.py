"""Local stand-in for API Gateway and S3 event delivery. Never deployed."""

import time
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, Response, request, send_from_directory

from src.common.config import get_settings
from src.common.log import get_logger
from src.common.storage import storage_client
from src.ingestion.handlers import get_status, get_upload_url, process_csv

UI_DIR = Path(__file__).resolve().parents[2] / "ui"
MINIO_WEBHOOK_ARN = "arn:minio:sqs::PRIMARY:webhook"

app = Flask(__name__, static_folder=None)
log = get_logger("local.app")


def _respond(result: dict[str, Any]) -> Response:
    return Response(result["body"], result["statusCode"], result["headers"])


@app.get("/")
def index() -> Response:
    return send_from_directory(UI_DIR, "index.html")


@app.get("/<path:filename>")
def ui_asset(filename: str) -> Response:
    return send_from_directory(UI_DIR, filename)


@app.post("/uploads")
def create_upload() -> Response:
    event = {"body": request.get_data(as_text=True)}
    return _respond(get_upload_url.handler(event, None))


@app.get("/uploads/<upload_id>")
def upload_status(upload_id: str) -> Response:
    return _respond(get_status.handler({"pathParameters": {"upload_id": upload_id}}, None))


@app.post("/events/s3")
def s3_event() -> Response:
    process_csv.handler(request.get_json(force=True, silent=True) or {}, None)
    return Response("{}", 200, {"Content-Type": "application/json"})


def prepare_bucket() -> None:
    """Create the bucket and subscribe this app to its ObjectCreated events."""
    settings = get_settings()
    s3 = storage_client(settings)
    for attempt in range(1, 31):
        try:
            try:
                s3.head_bucket(Bucket=settings.s3_bucket)
            except ClientError:
                s3.create_bucket(Bucket=settings.s3_bucket)
            s3.put_bucket_notification_configuration(
                Bucket=settings.s3_bucket,
                NotificationConfiguration={
                    "QueueConfigurations": [
                        {
                            "QueueArn": MINIO_WEBHOOK_ARN,
                            "Events": ["s3:ObjectCreated:*"],
                            "Filter": {
                                "Key": {"FilterRules": [{"Name": "prefix", "Value": "uploads/"}]}
                            },
                        }
                    ]
                },
            )
            log.info("bucket %s ready", settings.s3_bucket)
            return
        except (BotoCoreError, ClientError) as exc:
            log.warning("storage not ready (attempt %d): %s", attempt, exc)
            time.sleep(2)
    raise RuntimeError("object storage never became ready")


if __name__ == "__main__":
    prepare_bucket()
    app.run(host="0.0.0.0", port=8000)
