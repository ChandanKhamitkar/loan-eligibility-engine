# Directory Structure

Target layout (monorepo). Folders are created when first needed; this is the map.

```
loan-eligibility-engine/
├── README.md                  # Final deliverable: architecture diagram, setup, design decisions
├── serverless.yml             # AWS resources: S3, Lambdas, API Gateway, RDS
├── docker-compose.yml         # Local stack: Postgres, n8n, MinIO, local API adapter
├── docker-compose.aws.yml     # n8n only, run on the EC2 host in the AWS deployment
├── package.json               # Serverless Framework v3 + python-requirements plugin
├── requirements-lambda.txt    # Dependencies packaged into the Lambdas
├── .env.example               # All config keys, no secrets
├── pyproject.toml             # ruff + pytest config
├── requirements.txt           # runtime deps (+ requirements-dev.txt)
├── docker/                    # api.Dockerfile, postgres/init (creates n8n DB)
├── .gitignore
│
├── src/                       # All Python code
│   ├── admin/                 # migrate.py: Lambda that runs migrations inside the VPC
│   ├── web/                   # serve_ui.py: Lambda that serves ui/ from the API origin
│   ├── common/                # Shared by every service
│   │   ├── config.py          #   env vars, validated once
│   │   ├── db.py              #   connection helper
│   │   ├── storage.py         #   S3/MinIO client (endpoint from config)
│   │   ├── http.py            #   API response helper
│   │   └── log.py
│   ├── ingestion/             # CSV upload pipeline
│   │   ├── handlers/          #   thin Lambda entry points
│   │   │   ├── get_upload_url.py
│   │   │   ├── process_csv.py
│   │   │   └── get_status.py
│   │   ├── service.py         #   orchestrates one upload end to end
│   │   ├── parser.py          #   stream + chunk CSV
│   │   ├── validators.py      #   row validation + normalization (pure)
│   │   ├── repositories/      #   one module per table
│   │   │   ├── uploads.py     #     create, claim, finish, fail, get
│   │   │   ├── users.py       #     chunked upsert
│   │   │   └── upload_errors.py #   rejected rows
│   │   └── notify.py          #   call n8n webhook
│   └── local/
│       └── app.py             # Flask adapter: routes call the same handlers
│
├── ui/                        # Minimal upload page
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── n8n/
│   ├── workflows/             # Exported JSON, credentials stripped
│   │   ├── a_product_discovery.json
│   │   ├── b_user_matching.json
│   │   ├── c_notification.json
│   │   └── variants/          #   c_notification_ses.json: workflow C using AWS SES
│
├── db/
│   ├── migrations/            # Numbered, plain SQL: 0001_init.sql, ...
│   ├── queries/               # Reference copies of SQL used inside n8n (match_funnel.sql)
│   └── seed/                  # products.json: demo products for testing without the crawler
│
├── scripts/                   # migrate.py, seed_products.py, n8n_setup.py, aws_deploy.py, aws_teardown.py, generate_sample_users.py
├── tests/
│   ├── unit/                  # validators, parser, chunk dedupe
│   └── integration/           # upsert flags, funnel SQL on fixture data
│
├── data/                      # gitignored: sample CSVs (the assessment's, or generated)
├── docs/                      # aws-deployment.md; later the architecture diagram image and screenshots
└── planning/                  # Pre-build planning (this folder)
```

## Where things go

| I want to... | Look in |
|---|---|
| Change how a CSV row is validated | `src/ingestion/validators.py` |
| Change how users are saved | `src/ingestion/repositories/users.py` |
| Add a Lambda | `src/<domain>/handlers/` + entry in `serverless.yml` |
| Change matching rules | `n8n/workflows/b_user_matching.json` (SQL copy in `db/queries/`) |
| Change what the crawler extracts | `Build Gemini request` node in workflow A (prompt + schema) |
| Change the schema | new file in `db/migrations/` (never edit an applied one) |
| Add a crawl site | row in `crawl_sources` (seeded via migration or script) |
| Add a config value | `src/common/config.py` + `.env.example` |

## Conventions
- `handlers/` hold no business logic; they call modules beside them.
- `src/local/` exists only for local dev and is never deployed.
- `n8n/workflows/*.json` are exports; edit in the n8n UI, re-export, commit.
- Anything in `planning/` is context, not shipped behavior.
