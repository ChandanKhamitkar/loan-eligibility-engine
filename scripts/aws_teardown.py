"""Delete everything the AWS deployment created, so nothing keeps costing money.

Usage: python scripts/aws_teardown.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.aws"
SERVICE, STAGE = "loan-eligibility-engine", "aws"


def load_env() -> dict[str, str]:
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def main() -> None:
    env = load_env()
    region = env.get("DEPLOY_REGION", "ap-southeast-2")
    os.environ.update(env)
    session = boto3.Session(region_name=region)

    account = session.client("sts").get_caller_identity()["Account"]
    bucket = f"{SERVICE}-uploads-{account}-{region}"
    try:
        session.resource("s3").Bucket(bucket).objects.all().delete()
        print(f"emptied {bucket}")
    except ClientError as exc:
        print(f"bucket not emptied ({exc.response['Error']['Code']}); continuing")

    npx = shutil.which("npx") or sys.exit("Node.js (npx) is required")
    command = [npx, "serverless", "remove", "--stage", STAGE, "--region", region]
    subprocess.run(command, check=True, cwd=ROOT)
    print("Stack removed. Check the CloudFormation console to confirm nothing is left.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"command failed: {exc}")
