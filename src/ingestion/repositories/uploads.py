import uuid
from typing import Any

import psycopg


def create(conn: psycopg.Connection, filename: str) -> tuple[uuid.UUID, str]:
    upload_id = uuid.uuid4()
    object_key = f"uploads/{upload_id}.csv"
    conn.execute(
        "INSERT INTO uploads (upload_id, object_key, filename) VALUES (%s, %s, %s)",
        (upload_id, object_key, filename),
    )
    return upload_id, object_key


def claim(conn: psycopg.Connection, upload_id: uuid.UUID) -> bool:
    """Move uploaded -> processing; false if already claimed (duplicate event delivery)."""
    cur = conn.execute(
        "UPDATE uploads SET status = 'processing', updated_at = now() "
        "WHERE upload_id = %s AND status = 'uploaded'",
        (upload_id,),
    )
    return cur.rowcount == 1


def finish(
    conn: psycopg.Connection, upload_id: uuid.UUID, total: int, ok: int, rejected: int
) -> None:
    conn.execute(
        "UPDATE uploads SET status = 'processed', rows_total = %s, rows_ok = %s, "
        "rows_rejected = %s, updated_at = now() WHERE upload_id = %s",
        (total, ok, rejected, upload_id),
    )


def fail(conn: psycopg.Connection, upload_id: uuid.UUID, error: str) -> None:
    conn.execute(
        "UPDATE uploads SET status = 'failed', error = %s, updated_at = now() WHERE upload_id = %s",
        (error[:500], upload_id),
    )


def get(conn: psycopg.Connection, upload_id: uuid.UUID) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT upload_id, filename, status, rows_total, rows_ok, rows_rejected, error, "
        "created_at, updated_at FROM uploads WHERE upload_id = %s",
        (upload_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    columns = [col.name for col in cur.description]
    return dict(zip(columns, row, strict=True))
