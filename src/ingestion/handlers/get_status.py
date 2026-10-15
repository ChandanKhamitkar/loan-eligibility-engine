import uuid
from typing import Any

from src.common.config import get_settings
from src.common.db import connect
from src.common.http import json_response
from src.ingestion import repository


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        upload_id = uuid.UUID((event.get("pathParameters") or {}).get("upload_id", ""))
    except ValueError:
        return json_response(400, {"error": "Invalid upload id"})

    with connect(get_settings()) as conn:
        upload = repository.get_upload(conn, upload_id)
        if upload is None:
            return json_response(404, {"error": "Upload not found"})
        upload["rejected_samples"] = repository.get_issues(conn, upload_id)
    return json_response(200, upload)
