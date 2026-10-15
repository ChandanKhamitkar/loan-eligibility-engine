"""Apply numbered SQL migrations from db/migrations in order, once each."""

import sys
from pathlib import Path

from src.common.config import get_settings
from src.common.db import connect
from src.common.log import get_logger
from src.common.migrations import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"
log = get_logger("migrate")


def main() -> None:
    with connect(get_settings()) as conn:
        apply_migrations(conn, MIGRATIONS_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("migration failed")
        sys.exit(1)
