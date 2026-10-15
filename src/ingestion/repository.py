import json
import uuid
from typing import Any

import psycopg

from src.ingestion.parser import RowIssue
from src.ingestion.validators import UserRow

MAX_STORED_ERRORS = 1000

_UPSERT_USERS = """
INSERT INTO users (user_id, name, email, monthly_income, credit_score,
                   employment_status, age, last_upload_id)
SELECT *, %(upload_id)s::uuid
FROM unnest(%(user_ids)s::uuid[], %(names)s::text[], %(emails)s::text[],
            %(incomes)s::numeric[], %(scores)s::smallint[],
            %(employments)s::text[], %(ages)s::smallint[])
ON CONFLICT (user_id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    monthly_income = EXCLUDED.monthly_income,
    credit_score = EXCLUDED.credit_score,
    employment_status = EXCLUDED.employment_status,
    age = EXCLUDED.age,
    last_upload_id = EXCLUDED.last_upload_id,
    needs_match = users.needs_match OR (
        (users.monthly_income, users.credit_score, users.employment_status, users.age)
        IS DISTINCT FROM
        (EXCLUDED.monthly_income, EXCLUDED.credit_score, EXCLUDED.employment_status, EXCLUDED.age)
    ),
    updated_at = now()
WHERE (users.name, users.email, users.monthly_income, users.credit_score,
       users.employment_status, users.age)
      IS DISTINCT FROM
      (EXCLUDED.name, EXCLUDED.email, EXCLUDED.monthly_income, EXCLUDED.credit_score,
       EXCLUDED.employment_status, EXCLUDED.age)
"""


def create_upload(conn: psycopg.Connection, filename: str) -> tuple[uuid.UUID, str]:
    upload_id = uuid.uuid4()
    object_key = f"uploads/{upload_id}.csv"
    conn.execute(
        "INSERT INTO uploads (upload_id, object_key, filename) VALUES (%s, %s, %s)",
        (upload_id, object_key, filename),
    )
    return upload_id, object_key


def claim_upload(conn: psycopg.Connection, upload_id: uuid.UUID) -> bool:
    """Move uploaded -> processing; false if already claimed (duplicate event delivery)."""
    cur = conn.execute(
        "UPDATE uploads SET status = 'processing', updated_at = now() "
        "WHERE upload_id = %s AND status = 'uploaded'",
        (upload_id,),
    )
    return cur.rowcount == 1


def finish_upload(
    conn: psycopg.Connection, upload_id: uuid.UUID, total: int, ok: int, rejected: int
) -> None:
    conn.execute(
        "UPDATE uploads SET status = 'processed', rows_total = %s, rows_ok = %s, "
        "rows_rejected = %s, updated_at = now() WHERE upload_id = %s",
        (total, ok, rejected, upload_id),
    )


def fail_upload(conn: psycopg.Connection, upload_id: uuid.UUID, error: str) -> None:
    conn.execute(
        "UPDATE uploads SET status = 'failed', error = %s, updated_at = now() WHERE upload_id = %s",
        (error[:500], upload_id),
    )


def upsert_users(conn: psycopg.Connection, upload_id: uuid.UUID, users: list[UserRow]) -> None:
    if not users:
        return
    conn.execute(
        _UPSERT_USERS,
        {
            "upload_id": upload_id,
            "user_ids": [u.user_id for u in users],
            "names": [u.name for u in users],
            "emails": [u.email for u in users],
            "incomes": [u.monthly_income for u in users],
            "scores": [u.credit_score for u in users],
            "employments": [u.employment_status for u in users],
            "ages": [u.age for u in users],
        },
    )


def store_issues(
    conn: psycopg.Connection, upload_id: uuid.UUID, issues: list[RowIssue], already_stored: int
) -> int:
    """Persist rejected rows up to MAX_STORED_ERRORS per upload; return how many were stored."""
    room = MAX_STORED_ERRORS - already_stored
    batch = issues[: max(room, 0)]
    if batch:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO upload_errors (upload_id, line_no, raw, reason) "
                "VALUES (%s, %s, %s, %s)",
                [(upload_id, i.line_no, json.dumps(i.raw), i.reason) for i in batch],
            )
    return len(batch)


def get_upload(conn: psycopg.Connection, upload_id: uuid.UUID) -> dict[str, Any] | None:
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


def get_issues(conn: psycopg.Connection, upload_id: uuid.UUID, limit: int = 20) -> list[dict]:
    cur = conn.execute(
        "SELECT line_no, reason FROM upload_errors WHERE upload_id = %s ORDER BY line_no LIMIT %s",
        (upload_id, limit),
    )
    return [{"line_no": line_no, "reason": reason} for line_no, reason in cur.fetchall()]
