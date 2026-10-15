# AWS deployment

One command creates the whole stack; another deletes it. The local Docker setup is unchanged and still works without any of this.

```
Browser ──► API Gateway ──► Lambda (ui / get_upload_url / get_status)
   │                              │
   └─ presigned POST ─► S3 ──event──► Lambda process_csv ──► RDS Postgres (private)
                                              │ webhook (private IP)
                                              ▼
                         EC2: n8n (Docker) ──► RDS, Gemini, SES
```

Lambda, RDS and the n8n host share one VPC. RDS has no public access and accepts connections only from the Lambda and n8n security groups. There is no NAT gateway: Lambda reaches S3 through a free gateway endpoint and n8n over its private IP.

## Prerequisites

- An AWS account and an IAM user with access keys that can create the stack (for a short-lived demo, `AdministratorAccess`).
- Node.js 18+ (`npm install` once), Docker (packages the Linux build of `psycopg`), and the Python venv from the main README.
- **SES, in the region you deploy to** (default `ap-southeast-2`): verify the sender address and every address in `NOTIFY_RECIPIENTS`. New accounts are in the SES sandbox, which only sends to verified addresses. Create a separate IAM user with only `ses:SendEmail`, and keep its keys for step 1.

## Deploy

1. `cp .env.aws.example .env.aws` and fill it in. Use letters and digits only in `DB_PASSWORD`.
2. `npm install`
3. `python scripts/aws_deploy.py`

The script deploys the stack, uploads the n8n bundle (compose file, workflows, generated `.env`) to S3, then runs the database migrations through a Lambda inside the VPC. Expect 10-20 minutes the first time (RDS creation, Docker build of the Lambda dependencies).

4. The EC2 host installs Docker, pulls the bundle, starts n8n and imports the credentials and workflows by itself. Open the printed n8n URL once it answers, create the n8n owner account, and check that workflows A, B and C show as published.
5. Open the printed app URL, upload `data/demo_users.csv` (or `users.csv`), and watch the status steps. Run workflow A once from the n8n editor first so products exist.

## Updating a running deployment

`python scripts/aws_deploy.py --update-n8n` redeploys, runs new migrations, and re-applies the latest workflows and settings on the existing n8n host (through SSM Run Command). Without the flag the host only reads its bundle on first boot.

## Tear down

`python scripts/aws_teardown.py` empties the bucket and removes the stack (RDS, EC2, VPC, Lambdas). Do this as soon as the demo is recorded.

## Cost and limits

- The free plan gives credits and cannot bill you unless you upgrade to a paid plan. Do not upgrade.
- Rough running cost while deployed: an RDS micro plus an EC2 small instance is a few cents per hour. A budget alert only warns; it does not stop spending.
- Which instance types and services a free plan allows is shown in the console; set `N8N_INSTANCE_TYPE` to one that is allowed.
- Demo shortcuts, noted because production would differ: the database password is a CloudFormation parameter (use Secrets Manager or IAM auth), the n8n editor is plain HTTP restricted to `ADMIN_CIDR`, and the SES keys sit in the instance's `.env`.

## If the n8n host does not come up

Connect with Session Manager (EC2 console → Connect) and read `/var/log/cloud-init-output.log`. Common causes: the bundle was not uploaded (rerun the deploy script), or the instance type is not allowed on the account plan.
