import codecs
import uuid

import psycopg
from botocore.client import BaseClient

from src.common.config import Settings
from src.common.log import get_logger
from src.ingestion.notify import trigger_matching
from src.ingestion.parser import InvalidHeaderError, parse_chunks
from src.ingestion.repositories import upload_errors, uploads, users

log = get_logger(__name__)


def process_upload(
    conn: psycopg.Connection,
    s3: BaseClient,
    settings: Settings,
    upload_id: uuid.UUID,
    object_key: str,
) -> None:
    """Stream the uploaded CSV into `users`, then hand off to the matching workflow."""
    if not uploads.claim(conn, upload_id):
        log.info("upload %s already claimed, ignoring event", upload_id)
        return

    try:
        total, ok, rejected = _load_users(conn, s3, settings, upload_id, object_key)
    except InvalidHeaderError as exc:
        uploads.fail(conn, upload_id, f"Invalid CSV header: {exc}")
        return
    except Exception as exc:
        log.exception("processing failed for upload %s", upload_id)
        uploads.fail(conn, upload_id, f"Processing error: {exc}")
        return

    uploads.finish(conn, upload_id, total, ok, rejected)
    log.info("upload %s processed: %d rows, %d ok, %d rejected", upload_id, total, ok, rejected)

    if not trigger_matching(settings, upload_id):
        log.error("upload %s processed but matching was not triggered", upload_id)


def _load_users(
    conn: psycopg.Connection,
    s3: BaseClient,
    settings: Settings,
    upload_id: uuid.UUID,
    object_key: str,
) -> tuple[int, int, int]:
    body = s3.get_object(Bucket=settings.s3_bucket, Key=object_key)["Body"]
    lines = codecs.getreader("utf-8-sig")(body)

    total = ok = stored_errors = 0
    for chunk in parse_chunks(lines, settings.chunk_size):
        with conn.transaction():
            users.upsert(conn, upload_id, chunk.users)
            stored_errors += upload_errors.store(conn, upload_id, chunk.issues, stored_errors)
        total += chunk.rows_seen
        ok += chunk.valid_rows
    return total, ok, total - ok
