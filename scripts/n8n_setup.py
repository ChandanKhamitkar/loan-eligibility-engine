"""Load credentials and workflows from the repo into the running n8n container.

Runs on the host (local) or on the EC2 instance (AWS); both need Docker. Credentials are
built from .env and never written to disk outside the container. Usage:
python scripts/n8n_setup.py

Optional .env keys: APP_DB_HOST / APP_DB_SSL (RDS), EMAIL_PROVIDER=ses (default smtp).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / "n8n" / "workflows"
SES_VARIANT = "/workflows/variants/c_notification_ses.json"
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


def postgres_credential(env: dict[str, str]) -> dict:
    ssl = env.get("APP_DB_SSL", "disable")
    return {
        "id": "app-postgres",
        "name": "App Postgres",
        "type": "postgres",
        "data": {
            "host": env.get("APP_DB_HOST", "postgres"),
            "port": 5432,
            "database": env["POSTGRES_DB"],
            "user": env["POSTGRES_USER"],
            "password": env["POSTGRES_PASSWORD"],
            "ssl": ssl,
            # RDS certificates are not in n8n's trust store; the connection is still encrypted
            "allowUnauthorizedCerts": ssl != "disable",
            "maxConnections": 10,
        },
    }


def email_credentials(env: dict[str, str]) -> list[dict]:
    if env.get("EMAIL_PROVIDER", "smtp") == "ses":
        return [
            {
                "id": "aws-ses",
                "name": "AWS SES",
                "type": "aws",
                "data": {
                    "region": env["SES_REGION"],
                    "accessKeyId": env["SES_AWS_ACCESS_KEY_ID"],
                    "secretAccessKey": env["SES_AWS_SECRET_ACCESS_KEY"],
                },
            }
        ]
    if not env.get("GMAIL_APP_PASSWORD"):
        print("GMAIL_APP_PASSWORD is empty: skipping the SMTP credential (emails will fail).")
        return []
    return [
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
    ]


def main() -> None:
    env = read_env()
    credentials = [postgres_credential(env), *email_credentials(env)]
    n8n("sh", "-c", f"cat > {CREDENTIALS_FILE_IN_CONTAINER}", stdin=json.dumps(credentials))
    n8n("n8n", "import:credentials", f"--input={CREDENTIALS_FILE_IN_CONTAINER}")
    n8n("rm", "-f", CREDENTIALS_FILE_IN_CONTAINER)

    n8n("n8n", "import:workflow", "--separate", "--input=/workflows")
    if env.get("EMAIL_PROVIDER") == "ses":
        # Same workflow id, so this replaces the SMTP version of workflow C
        n8n("n8n", "import:workflow", f"--input={SES_VARIANT}")
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
