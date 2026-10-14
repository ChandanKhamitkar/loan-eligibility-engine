# Directory Structure

Target layout (monorepo). Folders are created when first needed; this is the map.

```
loan-eligibility-engine/
├── README.md                  # Final deliverable: architecture diagram, setup, design decisions
├── serverless.yml             # AWS resources: S3, Lambdas, API Gateway, RDS
├── docker-compose.yml         # Local stack: Postgres, n8n, MinIO, local API adapter
├── .env.example               # All config keys, no secrets
├── pyproject.toml             # ruff + pytest config, Python deps
├── .gitignore
│
├── src/                       # All Python code
│   ├── common/                # Shared by every service
│   │   ├── config.py          #   env vars, validated once
│   │   ├── db.py              #   connection helper
│   │   ├── storage.py         #   S3/MinIO client (endpoint from config)
│   │   └── logging.py
│   ├── ingestion/             # CSV upload pipeline
│   │   ├── handlers/          #   thin Lambda entry points
│   │   │   ├── get_upload_url.py
│   │   │   ├── process_csv.py
│   │   │   └── get_status.py
│   │   ├── parser.py          #   stream + chunk CSV
│   │   ├── validators.py      #   row validation + normalization (pure)
│   │   ├── repository.py      #   upsert users, update uploads
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
│   │   └── error_handler.json
│   └── prompts/               # LLM prompt + JSON schema for product extraction
│
├── db/
│   ├── migrations/            # Numbered, plain SQL: 0001_init.sql, ...
│   └── queries/               # Reference copies of SQL used inside n8n (funnel)
│
├── scripts/                   # migrate.py, seed_products.py (fallback demo products)
├── tests/
│   ├── unit/                  # validators, parser, chunk dedupe
│   └── integration/           # upsert flags, funnel SQL on fixture data
│
├── data/                      # users.csv (10k), demo_users.csv (~20 rows)
├── docs/                      # Final docs assets: architecture diagram image, setup guide, screenshots
└── planning/                  # Pre-build planning (this folder)
```

## Where things go

| I want to... | Look in |
|---|---|
| Change how a CSV row is validated | `src/ingestion/validators.py` |
| Change how users are saved | `src/ingestion/repository.py` |
| Add a Lambda | `src/<domain>/handlers/` + entry in `serverless.yml` |
| Change matching rules | `n8n/workflows/b_user_matching.json` (SQL copy in `db/queries/`) |
| Change what the crawler extracts | `n8n/prompts/` + workflow A |
| Change the schema | new file in `db/migrations/` (never edit an applied one) |
| Add a crawl site | row in `crawl_sources` (seeded via migration or script) |
| Add a config value | `src/common/config.py` + `.env.example` |

## Conventions
- `handlers/` hold no business logic; they call modules beside them.
- `src/local/` exists only for local dev and is never deployed.
- `n8n/workflows/*.json` are exports; edit in the n8n UI, re-export, commit.
- Anything in `planning/` is context, not shipped behavior.
