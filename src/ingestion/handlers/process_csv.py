import uuid
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote_plus

from src.common.config import get_settings
from src.common.db import connect
from src.common.log import get_logger
from src.common.storage import storage_client
from src.ingestion.service import process_upload

log = get_logger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """S3 ObjectCreated event (also the shape MinIO sends)."""
    settings = get_settings()
    s3 = storage_client(settings)
    with connect(settings) as conn:
        for record in event.get("Records", []):
            key = unquote_plus(record["s3"]["object"]["key"])
            upload_id = _upload_id_from_key(key)
            if upload_id is None:
                log.warning("ignoring object with unexpected key %s", key)
                continue
            process_upload(conn, s3, settings, upload_id, key)
    return {"ok": True}


def _upload_id_from_key(key: str) -> uuid.UUID | None:
    path = PurePosixPath(key)
    if path.parent.name != "uploads" or path.suffix != ".csv":
        return None
    try:
        return uuid.UUID(path.stem)
    except ValueError:
        return None
