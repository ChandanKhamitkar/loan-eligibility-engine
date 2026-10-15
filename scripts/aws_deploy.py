"""Deploy the AWS stack, ship the n8n bundle to its EC2 host, and run DB migrations.

Usage: python scripts/aws_deploy.py   (reads .env.aws; see .env.aws.example)

Order matters: the stack creates the EC2 host, which waits for a bundle in S3. This script
uploads that bundle once the stack exists (it needs the database host name), then migrates.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.aws"
SERVICE, STAGE = "loan-eligibility-engine", "aws"
STACK = f"{SERVICE}-{STAGE}"
BUNDLE_KEY = "bootstrap/n8n-bundle.tgz"
BUNDLE_FILES = ["docker-compose.aws.yml", "scripts/n8n_setup.py", "n8n/workflows"]
REQUIRED = ["DB_USER", "DB_PASSWORD", "DB_NAME", "WEBHOOK_SECRET", "N8N_ENCRYPTION_KEY",
            "GEMINI_API_KEY", "SES_FROM", "SES_AWS_ACCESS_KEY_ID", "SES_AWS_SECRET_ACCESS_KEY",
            "NOTIFY_RECIPIENTS"]  # fmt: skip


def load_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        sys.exit(f"{ENV_FILE.name} not found. Copy .env.aws.example and fill it in.")
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    missing = [key for key in REQUIRED if not env.get(key)]
    if missing:
        sys.exit(f"Missing in {ENV_FILE.name}: {', '.join(missing)}")
    if not env.get("ADMIN_CIDR"):
        with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as response:
            ip = response.read().decode().strip()
        env["ADMIN_CIDR"] = f"{ip}/32"
        print(f"ADMIN_CIDR not set; allowing n8n editor access from {env['ADMIN_CIDR']}")
    return env


def run_serverless(*args: str, env: dict[str, str]) -> None:
    npx = shutil.which("npx") or sys.exit("Node.js (npx) is required")
    subprocess.run([npx, "serverless", *args], check=True, cwd=ROOT, env={**os.environ, **env})


def stack_outputs(cloudformation) -> dict[str, str]:
    stack = cloudformation.describe_stacks(StackName=STACK)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}


def n8n_host_env(env: dict[str, str], outputs: dict[str, str]) -> str:
    values = {
        "COMPOSE_FILE": "docker-compose.aws.yml",
        "POSTGRES_DB": env["DB_NAME"],
        "POSTGRES_USER": env["DB_USER"],
        "POSTGRES_PASSWORD": env["DB_PASSWORD"],
        "APP_DB_HOST": outputs["DatabaseHost"],
        "APP_DB_SSL": "require",
        "EMAIL_PROVIDER": "ses",
        "SES_REGION": env.get("SES_REGION", env["DEPLOY_REGION"]),
        "SES_FROM": env["SES_FROM"],
        "SES_AWS_ACCESS_KEY_ID": env["SES_AWS_ACCESS_KEY_ID"],
        "SES_AWS_SECRET_ACCESS_KEY": env["SES_AWS_SECRET_ACCESS_KEY"],
        "WEBHOOK_SECRET": env["WEBHOOK_SECRET"],
        "N8N_ENCRYPTION_KEY": env["N8N_ENCRYPTION_KEY"],
        "GEMINI_API_KEY": env["GEMINI_API_KEY"],
        "GEMINI_MODEL": env.get("GEMINI_MODEL", "gemini-3.8-flash"),
        "NOTIFY_LIMIT": env.get("NOTIFY_LIMIT", "2"),
        "NOTIFY_RECIPIENTS": env["NOTIFY_RECIPIENTS"],
    }
    return "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"


def build_bundle(host_env: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in BUNDLE_FILES:
            archive.add(ROOT / name, arcname=name, filter=_skip_caches)
        data = host_env.encode()
        info = tarfile.TarInfo(".env")
        info.size, info.mode = len(data), 0o600
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _skip_caches(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    return None if "__pycache__" in info.name else info


def main() -> None:
    env = load_env()
    env["DEPLOY_REGION"] = env.get("DEPLOY_REGION", "ap-south-1")
    region = env["DEPLOY_REGION"]

    run_serverless("deploy", "--stage", STAGE, "--region", region, env=env)

    session = boto3.Session(region_name=region)
    outputs = stack_outputs(session.client("cloudformation"))
    bundle = build_bundle(n8n_host_env(env, outputs))
    session.client("s3").put_object(
        Bucket=outputs["UploadBucketName"],
        Key=BUNDLE_KEY,
        Body=bundle,
        ServerSideEncryption="AES256",
    )
    print(f"uploaded {BUNDLE_KEY} ({len(bundle):,} bytes)")

    response = session.client("lambda").invoke(FunctionName=f"{STACK}-migrate")
    result = json.loads(response["Payload"].read())
    if response.get("FunctionError"):
        sys.exit(f"migration failed: {result}")
    print(f"migrations applied: {result['applied'] or 'none (already up to date)'}")

    print("\nDeployed.")
    print(f"  App:  {outputs.get('HttpApiUrl')}")
    print(f"  n8n:  http://{outputs['N8nPublicIp']}:5678  (ready a few minutes after first boot)")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"command failed: {exc}")
