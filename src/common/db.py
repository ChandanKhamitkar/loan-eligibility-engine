import psycopg

from src.common.config import Settings


def connect(settings: Settings) -> psycopg.Connection:
    """Autocommit connection; callers open explicit transactions where they need one."""
    return psycopg.connect(settings.database_url, autocommit=True)
