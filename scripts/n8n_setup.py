"""Load credentials and workflows from the repo into the running n8n container.

Host-side helper (needs Docker). Credentials are built from .env and never written to disk
on the host. Usage: python scripts/n8n_setup.py
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / "n8n" / "workflows"
CREDENTIALS_FILE_IN_CONTAINER = "/tmp/credentials.json"


def read_env() -> dict[str, str]:
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def n8n(*args: str, stdin: str | None = None) -> None:
    command = ["docker", "compose", "exec", "-T", "n8n", *args]
    subprocess.run(command, input=stdin, text=True, check=True, cwd=ROOT)


def credentials(env: dict[str, str]) -> list[dict]:
    creds = [
        {
            "id": "app-postgres",
            "name": "App Postgres",
            "type": "postgres",
            "data": {
                "host": "postgres",
                "port": 5432,
                "database": env["POSTGRES_DB"],
                "user": env["POSTGRES_USER"],
                "password": env["POSTGRES_PASSWORD"],
                "ssl": "disable",
                "maxConnections": 10,
            },
        }
    ]
    if env.get("GMAIL_APP_PASSWORD"):
        creds.append(
            {
                "id": "gmail-smtp",
                "name": "Gmail SMTP",
                "type": "smtp",
                "data": {
                    "host": "smtp.gmail.com",
                    "port": 465,
                    "secure": True,
                    "user": env["GMAIL_USER"],
                    "password": env["GMAIL_APP_PASSWORD"],
                },
            }
        )
    else:
        print("GMAIL_APP_PASSWORD is empty: skipping the SMTP credential (emails will fail).")
    return creds


def main() -> None:
    env = read_env()
    n8n("sh", "-c", f"cat > {CREDENTIALS_FILE_IN_CONTAINER}", stdin=json.dumps(credentials(env)))
    n8n("n8n", "import:credentials", f"--input={CREDENTIALS_FILE_IN_CONTAINER}")
    n8n("rm", "-f", CREDENTIALS_FILE_IN_CONTAINER)

    n8n("n8n", "import:workflow", "--separate", "--input=/workflows")
    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        n8n("n8n", "publish:workflow", f"--id={workflow['id']}")

    # Webhook routes are registered at startup, so restart to pick up published workflows.
    subprocess.run(["docker", "compose", "restart", "n8n"], check=True, cwd=ROOT)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"n8n setup failed: {exc}")
