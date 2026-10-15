import boto3
from botocore.client import BaseClient
from botocore.config import Config

from src.common.config import Settings

_CLIENT_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "path"})


def _client(settings: Settings, endpoint_url: str | None) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=settings.aws_region,
        config=_CLIENT_CONFIG,
    )


def storage_client(settings: Settings) -> BaseClient:
    """Client for server-side calls (reads, bucket setup)."""
    return _client(settings, settings.s3_endpoint_url)


def presign_client(settings: Settings) -> BaseClient:
    """Client whose endpoint is the one the browser can reach.

    Locally the in-network MinIO host differs from the host the browser uses,
    and the signature is bound to the host.
    """
    return _client(settings, settings.s3_public_endpoint_url or settings.s3_endpoint_url)
