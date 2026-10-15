import json
from typing import Any


def json_response(status: int, payload: dict[str, Any]) -> dict[str, Any]:
    """API Gateway proxy-style response."""
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, default=str),
    }
