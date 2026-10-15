import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    s3_bucket: str
    s3_endpoint_url: str | None
    s3_public_endpoint_url: str | None
    aws_region: str
    max_upload_bytes: int
    chunk_size: int
    n8n_webhook_url: str | None
    webhook_secret: str


def _optional(name: str) -> str | None:
    return os.environ.get(name) or None


@lru_cache
def get_settings() -> Settings:
    missing = [name for name in ("DATABASE_URL", "S3_BUCKET") if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        s3_bucket=os.environ["S3_BUCKET"],
        s3_endpoint_url=_optional("S3_ENDPOINT_URL"),
        s3_public_endpoint_url=_optional("S3_PUBLIC_ENDPOINT_URL"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)),
        chunk_size=int(os.environ.get("CHUNK_SIZE", 2000)),
        n8n_webhook_url=_optional("N8N_WEBHOOK_URL"),
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
    )
