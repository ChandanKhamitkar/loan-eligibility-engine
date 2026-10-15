import json
from typing import Any

from src.common.config import get_settings
from src.common.db import connect
from src.common.http import json_response
from src.common.storage import presign_client
from src.ingestion import repository

_URL_TTL_SECONDS = 600


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    settings = get_settings()
    try:
        filename = str(json.loads(event.get("body") or "{}").get("filename", "")).strip()
    except json.JSONDecodeError:
        return json_response(400, {"error": "Body must be JSON"})
    if not filename.lower().endswith(".csv"):
        return json_response(400, {"error": "Only .csv files are accepted"})

    with connect(settings) as conn:
        upload_id, object_key = repository.create_upload(conn, filename[:255])

    post = presign_client(settings).generate_presigned_post(
        Bucket=settings.s3_bucket,
        Key=object_key,
        Fields={"Content-Type": "text/csv"},
        Conditions=[
            {"Content-Type": "text/csv"},
            ["content-length-range", 1, settings.max_upload_bytes],
        ],
        ExpiresIn=_URL_TTL_SECONDS,
    )
    return json_response(
        200,
        {"upload_id": str(upload_id), "url": post["url"], "fields": post["fields"]},
    )
