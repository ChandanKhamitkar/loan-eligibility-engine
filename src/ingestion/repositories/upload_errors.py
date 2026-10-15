import json
import uuid

import psycopg

from src.ingestion.parser import RowIssue

MAX_STORED = 1000


def store(
    conn: psycopg.Connection, upload_id: uuid.UUID, issues: list[RowIssue], already_stored: int
) -> int:
    """Persist rejected rows up to MAX_STORED per upload; return how many were stored."""
    room = MAX_STORED - already_stored
    batch = issues[: max(room, 0)]
    if batch:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO upload_errors (upload_id, line_no, raw, reason) "
                "VALUES (%s, %s, %s, %s)",
                [(upload_id, i.line_no, json.dumps(i.raw), i.reason) for i in batch],
            )
    return len(batch)


def list_for_upload(conn: psycopg.Connection, upload_id: uuid.UUID, limit: int = 20) -> list[dict]:
    cur = conn.execute(
        "SELECT line_no, reason FROM upload_errors WHERE upload_id = %s ORDER BY line_no LIMIT %s",
        (upload_id, limit),
    )
    return [{"line_no": line_no, "reason": reason} for line_no, reason in cur.fetchall()]
