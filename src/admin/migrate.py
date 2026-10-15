from pathlib import Path
from typing import Any

from src.common.config import get_settings
from src.common.db import connect
from src.common.migrations import apply_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Run inside the VPC because the database is not reachable from outside it."""
    with connect(get_settings()) as conn:
        return {"applied": apply_migrations(conn, MIGRATIONS_DIR)}
