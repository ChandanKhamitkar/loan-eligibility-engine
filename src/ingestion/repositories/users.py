import uuid

import psycopg

from src.ingestion.validators import UserRow

# One statement per chunk. A row identical to the stored one is not rewritten, and needs_match
# is raised only when a field that affects eligibility changed (name and email do not).
_UPSERT = """
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


def upsert(conn: psycopg.Connection, upload_id: uuid.UUID, rows: list[UserRow]) -> None:
    if not rows:
        return
    conn.execute(
        _UPSERT,
        {
            "upload_id": upload_id,
            "user_ids": [u.user_id for u in rows],
            "names": [u.name for u in rows],
            "emails": [u.email for u in rows],
            "incomes": [u.monthly_income for u in rows],
            "scores": [u.credit_score for u in rows],
            "employments": [u.employment_status for u in rows],
            "ages": [u.age for u in rows],
        },
    )
