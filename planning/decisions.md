# Loan Eligibility Engine: Decisions

Source brief: `The Loan Eligibility Engine (Engineering Intern)-clickpe.docx` (same folder).

## 1. Assessment essentials

**Mission:** ingest user CSV → discover loan products from public sites → match users to eligible products → email them. Automated end-to-end, orchestrated by self-hosted n8n.

| Item | Requirement |
|---|---|
| Backend | Python or Go |
| Cloud | AWS (Lambda, RDS Postgres, SES). API Gateway optional. Local deploy acceptable, public AWS deploy is a plus. No cloud spend expected. |
| Workflow engine | Self-hosted n8n (Docker Compose) |
| LLM | Any API; paid not required |
| IaC | `serverless.yml` (AWS resources) + `docker-compose.yml` (n8n) |
| Deliverables | Private GitHub repo (collaborators: ujjwalkala-clickpe, HarshSrivastav-Dailype, ManishBiswal-clickpe, tushar-clickpe), `serverless.yml`, `docker-compose.yml`, n8n workflow JSONs, README (architecture diagram, setup + credentials, design decisions, Treasure Hunt solution), 5-10 min video |
| Video | Walk through each workflow's nodes, live end-to-end run, show a received email |
| Deadline | 72 hours from assignment email |
| Scoring | n8n workflows 30 · Backend + code quality 30 · Cloud architecture 20 · Docs + video 20 |
| Email rule | Never email CSV addresses. Send only to own test aliases (`name+one@gmail.com`). |
| Upload rule | Must not be a plain Lambda/API Gateway file POST; use an event-driven pattern |
| UI | Minimal; upload CSV only |
| Note | They expect you to understand and explain every part of your own system |

**Out of scope:** auth, OAuth, passwords, user accounts, 10M-user scale.

## 2. Stack and environment

| Area | Decision |
|---|---|
| Language | Python |
| Phase 1 (build) | Everything local in Docker Compose: Postgres, n8n, S3-compatible storage (MinIO if its image/licence works, else a simple local upload service), processor service |
| Phase 2 (after it works) | Real AWS: S3 + Lambda + RDS via `serverless.yml`. Cloudflare R2 only as fallback (cannot trigger Lambda). |
| Email | Gmail SMTP (app password) first; swap to AWS SES node after everything works. Email body built in its own node so only the send node changes. |
| LLM | Gemini Flash, structured JSON output (response schema). No PII (no emails/names) in prompts. |
| Python libs | Plain handlers + `boto3`, `psycopg` 3, stdlib `csv`. Flask only as a local adapter around the same handlers. No Django, pandas or ORM. |
| DB | One Postgres server, two databases (`app`, `n8n`). Plain numbered SQL migrations. See [schema.md](schema.md). |
| Secrets | In n8n credential store and env vars, never in workflow JSON |

## 3. End-to-end flow

```
UI ──1 request upload──> backend ──presigned URL──> UI
UI ──2 PUT file directly──> object storage (bucket)
bucket ──3 ObjectCreated event──> CSV processor (Lambda in cloud)
processor ──4 validate + chunked upsert──> Postgres.users (flags changed rows needs_match)
processor ──5 webhook (upload_id, secret header)──> n8n Workflow B
B ──SQL funnel──> matches ──6 calls──> Workflow C ──email──> test inbox
Workflow A (daily cron): 5 sites → clean → hash → LLM extract → loan_products
```

## 4. Ingestion

- **Pattern:** presigned URL (browser uploads straight to bucket) + bucket event triggers the processor. Avoids API Gateway/Lambda payload and timeout limits and decouples upload from parsing.
- **Parsing:** stream the CSV, validate per row, insert in chunks. Parse logic is a standalone function, independent of the Lambda handler.
- **Duplicates:** upsert on `user_id`, latest row wins. Dedupe inside each chunk (keep last) before the upsert. Set `needs_match = true` only when values actually changed.
- **Rejected rows:** counted and stored per upload; they don't fail the batch.
- **`uploads` table:** `upload_id`, status (`processing → done → matched → notified`), `rows_ok`, `rows_rejected`.

### Data facts (`data/users.csv`)

| Fact | Value |
|---|---|
| Columns | user_id, **name**, email, monthly_income, credit_score, employment_status, age |
| Rows | 10,000 |
| Duplicate user_ids / blanks / bad values | none |
| monthly_income | 25,000 – 150,000 |
| credit_score | 650 – 800 |
| age | 22 – 50 |
| employment_status | Salaried (3,389), Self-Employed (3,371), Business (3,240) |
| Emails | 2,403 are shared across different user_ids → **email is not a key**; `user_id` is |

The sample is clean, so keep validation anyway (the grader may use another file). Also keep a ~20-row demo CSV for the video.

## 5. Workflow A: product discovery (daily cron)

1. Read the site list from config (**5 sites**; list-driven so adding one is a config change). Get 2-3 working first.
2. HTTP GET each page (polite: robots.txt, User-Agent, one fetch per day).
3. Clean: strip script/style/nav/footer/svg, keep table content as text, collapse whitespace.
4. Hash the **cleaned** text. Unchanged → skip.
5. Changed → send to Gemini with a fixed JSON schema (array of products, nullable fields); save hash + cleaned text on the `crawl_sources` row (latest snapshot only).
6. Validate in a Code node, then upsert `loan_products` on (lender, product_name). New or criteria-changed products set `needs_rematch`. Unseen for N days → mark inactive, never delete. An empty crawl never wipes the table.

Columns: see [schema.md](schema.md).

A small seed JSON of products exists only as a demo safety net.

## 6. Workflow B: matching (webhook)

- **Trigger:** webhook from the processor with `upload_id` and a shared-secret header. No DB triggers.
- **Scope:** a (user, product) pair is evaluated if the user has `needs_match` **or** the product has `needs_rematch` (flagged users × all products ∪ all users × flagged products). Claiming flags, clearing stale unnotified matches and inserting new ones happen in one transaction.
- **Optimization Treasure Hunt (core idea):** extract once, match deterministically. The LLM runs O(products) times at crawl time, never O(users × products). The LLM never sees the DB; n8n queries and passes only what's needed.

| Stage | Where | Logic |
|---|---|---|
| 0 | SQL | Only flagged users, only active products |
| 1 | SQL (one set-based join) | income ≥ min_income, score ≥ min_score, age in range, employment allowed. Null criterion = no constraint. |
| 2 | Rank + cap | `fit_score` = 100 − lowest rate, stored per match. The top-5 cap is applied in Workflow C when emailing, so partial re-evaluations never see a user's full list. |
| 3 (optional, small) | Gemini | Only products with `residual_criteria` and users who passed stage 1, per user bucket (income band × score band × employment), cached by hash. Also usable for a cached "why you match" blurb. |

- **Writes:** `matches` with PK (`user_id`, `product_id`), stage, fit_score, `notified=false`. Clears `needs_match`.
- **README must show funnel numbers** (pairs → after SQL → after rules → LLM calls).
- **Hand-off:** B calls C when finished.

## 7. Workflow C: notification

- Called by B (Execute Workflow node), or run manually from the n8n UI.
- Picks up to `NOTIFY_LIMIT` users (default **2**) with unnotified matches, most matches first. Each email lists the user's **best 5** products (by `fit_score`); all of that user's pending matches are then marked notified.
- **Demo guard:** recipients come only from `NOTIFY_RECIPIENTS` (round-robin), never from the CSV; the cap is enforced both in the SQL `LIMIT` and again in the email-building node. The cap is **per run**.
- `matches.notified = true` only after a successful send; a failed send stays pending.
- Gmail SMTP now (credential built from `.env` by `scripts/n8n_setup.py`); swap the send node to AWS SES later. Email building is a separate node.
- After the run, uploads in `matched` become `notified`. In demo mode this means "this run's emails were sent", not that all 10k users were emailed.

## 8. Edge cases

| Case | Handling |
|---|---|
| Bad / missing CSV fields | Reject row, count it, continue |
| Same file re-uploaded | Upsert; unchanged rows don't set `needs_match` |
| Duplicate user_id inside one file | Dedupe in chunk, last wins |
| Rerun of B | `matches` PK makes it idempotent |
| Webhook lost or n8n down | Retry with backoff; upload status shows stuck state; optional sweeper schedule |
| Crawl blocked / empty / layout change | Keep old products, hash + LLM re-extract, seed fallback |
| LLM rate limit / invalid JSON | Retry, schema-validate, fall back to rule-only result |
| Null product criteria | Treated as no constraint |
| Many users match many products | Cap top N per user; `NOTIFY_LIMIT` in demo |
| n8n unauthorized webhook call | Shared-secret header |

## 9. Open items to verify

- Which of the 5 candidate sites return rates and eligibility in raw HTML.
- Whether MinIO's current image/licence is usable; otherwise use the simple local upload service.
- Whether n8n's SES node works against the chosen setup (else real SES sandbox for that step only).
- AWS free-tier/credit status at signup, for phase 2.
