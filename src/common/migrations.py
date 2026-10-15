from pathlib import Path

import psycopg

from src.common.log import get_logger

log = get_logger(__name__)


def apply_migrations(conn: psycopg.Connection, directory: Path) -> list[str]:
    """Apply numbered .sql files once each, in order. Returns the names applied now."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    done = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}
    applied = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        log.info("applied %s", path.name)
        applied.append(path.name)
    return applied
