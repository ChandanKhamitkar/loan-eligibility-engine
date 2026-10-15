"""Apply numbered SQL migrations from db/migrations in order, once each."""

import sys
from pathlib import Path

import psycopg

from src.common.config import get_settings
from src.common.log import get_logger

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"
log = get_logger("migrate")


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            log.info("applied %s", path.name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("migration failed")
        sys.exit(1)
