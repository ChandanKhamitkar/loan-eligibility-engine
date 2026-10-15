import json
import time
import urllib.error
import urllib.request
import uuid

from src.common.config import Settings
from src.common.log import get_logger

log = get_logger(__name__)

_ATTEMPTS = 3
_TIMEOUT_SECONDS = 10


def trigger_matching(settings: Settings, upload_id: uuid.UUID) -> bool:
    """POST the n8n matching webhook, retrying with backoff. Returns whether it was accepted."""
    if not settings.n8n_webhook_url:
        log.warning("N8N_WEBHOOK_URL not set; skipping matching trigger for %s", upload_id)
        return False

    request = urllib.request.Request(
        settings.n8n_webhook_url,
        data=json.dumps({"upload_id": str(upload_id)}).encode(),
        headers={"Content-Type": "application/json", "X-Webhook-Secret": settings.webhook_secret},
        method="POST",
    )
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):
                return True
        except (urllib.error.URLError, TimeoutError) as exc:
            log.warning("matching trigger attempt %d/%d failed: %s", attempt, _ATTEMPTS, exc)
            if attempt < _ATTEMPTS:
                time.sleep(2**attempt)
    return False
