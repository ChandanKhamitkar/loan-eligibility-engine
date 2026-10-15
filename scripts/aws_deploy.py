"""Deploy the AWS stack, ship the n8n bundle to its EC2 host, and run DB migrations.

Usage: python scripts/aws_deploy.py [--update-n8n]   (reads .env.aws; see .env.aws.example)

--update-n8n re-applies the bundle on an already running n8n host (new workflows or settings);
without it the host only reads the bundle on its first boot.

Order matters: the stack creates the EC2 host, which waits for a bundle in S3. This script
uploads that bundle once the stack exists (it needs the database host name), then migrates.
"""

from __future__ import annotations

import contextlib
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
from botocore.exceptions import WaiterError

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
        "GEMINI_FALLBACK_MODEL": env.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
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


def refresh_n8n_host(session: boto3.Session, bucket: str, region: str) -> None:
    """Pull the latest bundle onto the running host through SSM and re-import the workflows."""
    cloudformation = session.client("cloudformation")
    detail = cloudformation.describe_stack_resource(
        StackName=STACK, LogicalResourceId="N8nInstance"
    )
    instance_id = detail["StackResourceDetail"]["PhysicalResourceId"]
    commands = [
        "set -e",
        "export HOME=/root",
        f"export AWS_DEFAULT_REGION={region}",
        "cd /opt/app",
        f"aws s3 cp s3://{bucket}/{BUNDLE_KEY} /tmp/bundle.tgz",
        "tar -xzf /tmp/bundle.tgz -C /opt/app",
        "TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token"
        " -H 'X-aws-ec2-metadata-token-ttl-seconds: 300')",
        'IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN"'
        " http://169.254.169.254/latest/meta-data/public-ipv4)",
        'echo "N8N_PUBLIC_URL=http://$IP:5678" >> .env',
        "docker compose up -d",
        "until curl -sf http://localhost:5678/healthz; do sleep 5; done",
        "python3 scripts/n8n_setup.py",
    ]
    ssm = session.client("ssm")
    sent = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands},
        TimeoutSeconds=900,
    )
    command_id = sent["Command"]["CommandId"]
    print(f"refreshing n8n host {instance_id} (command {command_id})...")
    # A failed command raises here; the invocation status below says what went wrong
    with contextlib.suppress(WaiterError):
        ssm.get_waiter("command_executed").wait(
            CommandId=command_id,
            InstanceId=instance_id,
            WaiterConfig={"Delay": 10, "MaxAttempts": 90},
        )
    result = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
    print(f"  status: {result['Status']}")
    if result["Status"] != "Success":
        print(result.get("StandardErrorContent", "")[-1500:])
        sys.exit("n8n host refresh failed")


def main() -> None:
    env = load_env()
    env["DEPLOY_REGION"] = env.get("DEPLOY_REGION", "ap-southeast-2")
    region = env["DEPLOY_REGION"]
    # Serverless loads .env.aws itself; boto3 needs the same AWS_* credentials in this process
    for key, value in env.items():
        os.environ.setdefault(key, value)

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

    if "--update-n8n" in sys.argv:
        refresh_n8n_host(session, outputs["UploadBucketName"], region)

    print("\nDeployed.")
    print(f"  App:  {outputs.get('HttpApiUrl')}")
    print(f"  n8n:  http://{outputs['N8nPublicIp']}:5678  (ready a few minutes after first boot)")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"command failed: {exc}")
