"""Delete everything the AWS deployment created, so nothing keeps costing money.

Usage: python scripts/aws_teardown.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.aws"
SERVICE, STAGE = "loan-eligibility-engine", "aws"
ATTEMPTS, WAIT_MINUTES = 4, 8
MANUAL_STEPS = (
    "Teardown did not finish. In the CloudFormation console, open the stack, choose Delete and "
    "tick 'Retain' for the resources that failed. What remains (VPC, subnets, security groups, "
    "gateway endpoint) is free; delete the VPC from the VPC console once its network "
    "interfaces are gone. Confirm no RDS or EC2 instance is left."
)


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
    for attempt in range(1, ATTEMPTS + 1):
        try:
            subprocess.run(command, check=True, cwd=ROOT)
            print("Stack removed. Check the CloudFormation console to confirm nothing is left.")
            return
        except subprocess.CalledProcessError:
            print_costly_resources(session)
            if attempt == ATTEMPTS:
                sys.exit(MANUAL_STEPS)
            # Lambda network interfaces can take up to ~30 minutes to release, which blocks
            # detaching the internet gateway; deleting again later normally succeeds.
            print(
                f"Delete failed (attempt {attempt}/{ATTEMPTS}); retrying in {WAIT_MINUTES} min..."
            )
            time.sleep(WAIT_MINUTES * 60)


def print_costly_resources(session: boto3.Session) -> None:
    """Show whether the two resources that cost money are already gone."""
    cloudformation = session.client("cloudformation")
    for logical_id in ("Database", "N8nInstance"):
        try:
            detail = cloudformation.describe_stack_resource(
                StackName=f"{SERVICE}-{STAGE}", LogicalResourceId=logical_id
            )["StackResourceDetail"]
            print(f"  {logical_id}: {detail['ResourceStatus']}")
        except ClientError:
            print(f"  {logical_id}: not found")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(f"command failed: {exc}")
