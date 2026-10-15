from pathlib import Path
from typing import Any

UI_DIR = Path(__file__).resolve().parents[2] / "ui"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Serve the UI from the API origin so the page needs no CORS or base URL."""
    name = (event.get("pathParameters") or {}).get("file") or "index.html"
    path = (UI_DIR / name).resolve()
    if path.parent != UI_DIR or path.suffix not in CONTENT_TYPES or not path.is_file():
        return {"statusCode": 404, "body": "Not found"}
    return {
        "statusCode": 200,
        "headers": {"Content-Type": CONTENT_TYPES[path.suffix], "Cache-Control": "no-cache"},
        "body": path.read_text(encoding="utf-8"),
    }
