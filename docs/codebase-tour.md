# Codebase tour

Read the stops in order. Each one says what to open, what to look for, and what it connects to next. About 2 hours end to end; the SQL and the three workflows are where the real logic is.

## The whole thing in one paragraph

A user picks a CSV in the browser. The browser asks the backend for a one-time upload link and sends the file **straight to object storage**, which fires an event. A function reads the file, validates each row, saves users to Postgres, and calls **n8n**. n8n runs three workflows: **A** (daily) reads lender web pages and uses an LLM to turn them into structured loan products; **B** (after each upload) matches users to products with one SQL statement; **C** (after B) emails matched users. Everything is plain code plus plain SQL; the only "smart" part is the LLM turning messy web text into columns.

```
 UI ─► get_upload_url ─► (file goes to storage) ─► process_csv ─► Postgres.users
                                                        │ webhook
                                                        ▼
        Workflow A (daily) ─► loan_products ─► Workflow B ─► matches ─► Workflow C ─► email
```

---

## Stop 1: The data model (start here, everything else reads or writes it)

Open [db/migrations/0001_init.sql](../db/migrations/0001_init.sql).

| Table | Think of it as | Written by | Read by |
|---|---|---|---|
| `uploads` | one row per CSV upload, with a status | UI request, parser, B, C | UI status polling |
| `users` | the people from the CSV | CSV parser | B |
| `crawl_sources` | the list of sites + last page fingerprint | A | A |
| `loan_products` | structured products | A | B, C |
| `matches` | which user qualifies for which product | B | C |
| `upload_errors` | rejected rows and why | parser | UI |

Notice three columns, they drive the whole design:
- `users.needs_match` (true = "B has not evaluated this user yet")
- `loan_products.needs_rematch` (true = "new or changed product, evaluate everyone against it")
- `matches.notified` (false = "C has not emailed this yet")

Then skim `0002` (`match_runs`, B's run log), `0003` (the three crawl sites), `0004` (`last_error`). Connects to: every later stop.

## Stop 2: Shared plumbing (5 small files)

All in [src/common/](../src/common/). Read them in 5 minutes:
- `config.py`: every setting comes from an environment variable, read once (`get_settings`). Local and AWS differ only here.
- `db.py`: `connect()` opens a Postgres connection.
- `storage.py`: S3 clients. Note `endpoint_url`: set locally (MinIO), empty on AWS (real S3). That one setting is how the same code runs in both places. `presign_client` exists because the browser must reach the storage by a different address than the server does locally.
- `http.py`, `log.py`: response shape and logging helpers.

## Stop 3: The browser

[ui/index.html](../ui/index.html) and [ui/app.js](../ui/app.js). In `app.js` follow three functions in order:
1. `requestUpload` → `POST /uploads` (asks for a permit)
2. `sendToStorage` → posts the file **directly to storage** (never through our server)
3. `poll` → `GET /uploads/{id}`, drawing the status steps until `notified`. It starts at 1.5 s, slows to 5 s, and gives up after 25 tries (about 1m45s) and shows a **Refresh status** button instead of polling forever

Connects to: the two handlers in stops 5 and 8.

## Stop 4: Who answers the browser? (the local/AWS split)

- Locally: [src/local/app.py](../src/local/app.py), a tiny Flask app. Each route just calls a handler. `prepare_bucket` creates the bucket and tells MinIO to POST an event to `/events/s3`.
- On AWS: API Gateway and S3 do this job, declared in [serverless.yml](../serverless.yml). There is no Flask there.

Key idea: **the handlers are the real code; Flask and API Gateway are just different ways to call them.**

## Stop 5: Getting an upload permit

[src/ingestion/handlers/get_upload_url.py](../src/ingestion/handlers/get_upload_url.py):
1. checks the filename ends in `.csv`
2. `uploads.create` ([repositories/uploads.py](../src/ingestion/repositories/uploads.py)) inserts an `uploads` row (status `uploaded`, key `uploads/<id>.csv`)
3. `generate_presigned_post` returns a signed form that allows exactly one upload, up to `MAX_UPLOAD_BYTES`, for 10 minutes

Why this design: the file never touches our API, so there are no request-size or timeout limits.

## Stop 6: The file lands; the event fires

[src/ingestion/handlers/process_csv.py](../src/ingestion/handlers/process_csv.py). It receives the storage event, extracts the object key, and `_upload_id_from_key` makes sure it looks like `uploads/<uuid>.csv` (ignores anything else). Then it calls `service.process_upload`. Locally the event arrives from MinIO via Flask; on AWS directly from S3.

## Stop 7: The heart of ingestion (read these 4 files together)

Start in [src/ingestion/service.py](../src/ingestion/service.py), `process_upload`:

1. `uploads.claim`: flips `uploaded → processing` only if it was `uploaded`. This stops duplicate event deliveries from processing a file twice.
2. `_load_users` opens the file as a stream and loops over `parser.parse_chunks`.
3. Per chunk of 2,000 rows, in one transaction: `users.upsert` and `upload_errors.store`.
4. On a bad header → `fail_upload`. On any other crash → `fail_upload` with the message.
5. `finish_upload` → status `processed`, then `notify.trigger_matching` calls n8n.

Now open the helpers it uses:
- [parser.py](../src/ingestion/parser.py): reads rows, calls the validator, builds chunks, collapses duplicate `user_id`s inside a chunk (last wins). A bad row becomes a `RowIssue` with its line number instead of stopping everything.
- [validators.py](../src/ingestion/validators.py): `validate_row` and its small `_parse_*` functions: UUID format, email, income > 0, score 300-900, age 18-100, employment name normalised (`self employed` → `Self-Employed`).
- [repositories/](../src/ingestion/repositories/): one small file per table. `uploads.py` (the status lifecycle), `users.py`, `upload_errors.py`. Read `_UPSERT` in `users.py` slowly. It inserts a whole chunk in one statement; on a clash (`ON CONFLICT (user_id)`) it updates the row; it sets `needs_match = true` **only if** income, score, employment or age actually changed; a row identical in every column is not rewritten at all.
- [notify.py](../src/ingestion/notify.py): `trigger_matching` POSTs `{upload_id}` to n8n with the secret header, retrying 3 times.

Connects to: Workflow B's webhook.

## Stop 8: Closing the loop for the UI

[src/ingestion/handlers/get_status.py](../src/ingestion/handlers/get_status.py) reads one `uploads` row (plus up to 20 rejection reasons). That is all the browser polls.

## Stop 9: How n8n gets its workflows

1. [docker-compose.yml](../docker-compose.yml): the cast of containers. `postgres` (also creates a second database for n8n itself), `minio` (storage; sends events to `api`), `migrate` (runs once, applies the SQL files), `api` (Flask), `n8n` (mounts `n8n/workflows/` read-only).
2. [scripts/n8n_setup.py](../scripts/n8n_setup.py): builds the database/email credentials from `.env`, pipes them into the n8n container, imports the three workflow JSON files, publishes them, restarts n8n. This is why no secrets sit in the workflow files.
3. Workflow nodes read configuration as `$env.NAME` (webhook secret, Gemini key, email limit, recipients).

## Stop 10: Workflow B, matching ([n8n/workflows/b_user_matching.json](../n8n/workflows/b_user_matching.json))

Open it in the n8n editor (easier than the JSON). Node order:
`Webhook` → `Secret and payload valid?` (no → `Reject 401`) → `Accept 202` (replies immediately) → `Mark upload matching` → `Run matching funnel` → `Mark upload matched` → `Run notification workflow` (this is C). If the funnel errors → `Mark upload failed`.

The one node that matters is `Run matching funnel`; its SQL lives in [db/queries/match_funnel.sql](../db/queries/match_funnel.sql). Read it CTE by CTE:
- `claimed_users` / `claimed_products`: grab everything flagged and clear the flags, atomically.
- `scope`: pair each claimed user with all active products, and every user with claimed products.
- `eligible`: keep pairs passing the hard rules (null = no constraint).
- `removed`: delete stale unnotified matches in scope.
- `written`: save matches (`ON CONFLICT` keeps it re-runnable).
- final `INSERT INTO match_runs`: records the funnel numbers.

## Stop 11: Workflow C, notification ([c_notification.json](../n8n/workflows/c_notification.json))

`Called by workflow B` → `Select users to notify` ([db/queries/notify_pending.sql](../db/queries/notify_pending.sql): up to `NOTIFY_LIMIT` users, best 5 products each) → `Build email` (HTML; recipient comes from `NOTIFY_RECIPIENTS`, **never** the CSV) → `Send email` → `Mark user matches notified` (only after a successful send) → `All sent` → `Mark uploads notified`. A failed send goes to `Send failed, left pending`.

## Stop 12: Workflow A, product discovery ([a_product_discovery.json](../n8n/workflows/a_product_discovery.json))

`Daily at 02:00` / `Run manually` → `Load enabled sources` → `Fetch page` → `Clean and hash` (strips markup, SHA-256 of the cleaned text) → `Page changed?` which routes three ways:
- `bad_page` → `Record fetch failure`
- `unchanged` → `Touch unchanged source` (no LLM call)
- `changed` → `Build Gemini request` (the prompt and JSON schema live in this node) → `Extract products (Gemini)` → on error `Extract products (fallback model)` → `Validate products` (range and enum checks) → `Any valid products?` → `Save products and snapshot` (one SQL statement: upsert products **and** store the hash) or `Record extract failure`.

A parallel branch, `Deactivate stale products`, switches off crawled products not seen for 7 days.

## Stop 13: Tests

[tests/unit/](../tests/unit/): `test_validators.py` and `test_parser.py` show exactly what a good and a bad row look like. Reading them is the fastest way to remember the rules.

## Stop 14: AWS (do this last)

Read the section after the trace below, then [serverless.yml](../serverless.yml) top to bottom: `functions:` (the 5 Lambdas), then `Resources:` (network, security groups, database, bucket, n8n host), then [scripts/aws_deploy.py](../scripts/aws_deploy.py) and [docker-compose.aws.yml](../docker-compose.aws.yml).

---

## Trace one row end to end

User `b35de23e…` (Dhruv Iyengar): income 131,000, score 725, Self-Employed, age 37.

1. UI posts the CSV to storage. `process_csv` runs; `validate_row` accepts it; `upsert_users` inserts the user with `needs_match = true`.
2. `trigger_matching` calls B. The funnel claims him and pairs him with every active product.
3. Against the real products: IDFC FIRST Bank passes (score 725 ≥ 710, age 37 within 21-60, Self-Employed allowed). ICICI Self-Employed fails (needs 750). Tata fails (Salaried only). A `matches` row is written for IDFC.
4. C selects users with pending matches (up to 2). If he is picked, he gets an email listing IDFC, the match is marked `notified`, and he is never emailed again.

Try it yourself in psql (`docker compose exec postgres psql -U <user> -d <db>`):
```sql
SELECT * FROM users WHERE user_id = 'b35de23e-755f-4c6a-81d8-f7dd99ce53ef';
SELECT p.lender, p.product_name, m.fit_score, m.notified
FROM matches m JOIN loan_products p USING (product_id)
WHERE m.user_id = 'b35de23e-755f-4c6a-81d8-f7dd99ce53ef';
SELECT * FROM match_runs ORDER BY run_id;
```

---

## What each AWS service is for, and why

The question for every piece is: **what problem does it solve that the local version solved with a Docker container?**

| AWS service | Role here | Problem it solves | Local equivalent |
|---|---|---|---|
| **S3** | Holds the uploaded CSV | Takes big files directly from the browser, so our code never carries them. Fires an event when a file lands. | MinIO |
| **API Gateway** | Public HTTPS address for 4 routes | A front door that gives Lambdas a URL, routes requests, and handles TLS | Flask routes |
| **Lambda** | `ui`, `getUploadUrl`, `getStatus`, `processCsv`, `migrate` | Runs a function only when something happens, with no server to manage and no cost while idle | Flask handlers / `api` container |
| **RDS** (PostgreSQL) | The database | A managed Postgres: patching, storage and failure handling are AWS's job. The brief requires it. | `postgres` container |
| **EC2** | Runs n8n in Docker | Lambda cannot host n8n. n8n is a long-running server with a UI, a scheduler and webhooks, and it must stay on. | `n8n` container |
| **VPC, subnets, security groups** | A private network | RDS is not reachable from the internet; only Lambda and n8n may connect to it | Docker's internal network |
| **IAM roles** | Permissions for Lambda and EC2 | Gives each piece only the access it needs (e.g. Lambda may read the upload bucket, nothing else) | none needed |
| **SES** | Sends the emails | Email delivery with proper sending infrastructure and limits | Gmail SMTP |
| **CloudFormation** (via Serverless) | Creates and deletes everything from `serverless.yml` | The whole stack as code: one command up, one command down | `docker compose up/down` |
| **Systems Manager (SSM)** | Pushes updates to / opens a shell on the EC2 host | Reach the server without opening SSH to the internet | none |
| **CloudWatch Logs** | Lambda logs (automatic) | Where to look when a function fails | `docker logs` |

### Lambda or EC2? A simple rule

| Ask yourself | If yes |
|---|---|
| Is the work **triggered by an event** and **finished in seconds to minutes**? | **Lambda** (parse a file when it lands; answer one web request) |
| Does it need to **run all the time**, keep its own state, expose its own UI or run its own schedule? | **EC2** or a container (n8n; a database; a game server) |
| Does the load come in **bursts with long idle gaps**? | **Lambda**: you pay nothing while idle |
| Does it run **longer than 15 minutes**, or need a custom runtime? | **EC2** / containers |

In this project: the CSV parser is Lambda because it wakes up only when a file arrives. n8n is EC2 because it has to exist continuously so its daily schedule fires and its webhook is always listening.

### Things worth being able to explain
- **Why not parse the CSV on EC2 too?** It would work, but you pay for it 24/7 for a job that runs for seconds, you handle scaling yourself, and the brief asks for an event-driven design.
- **Why is the database private?** Nothing needs to reach it from the internet. Lambda (inside the VPC) and n8n (same VPC) are the only clients, so the security group only admits those two.
- **Why no NAT gateway?** A NAT lets private things reach the internet but costs about $32/month. Our Lambdas only need the VPC and S3, and S3 has a free "gateway endpoint". n8n sits in a public subnet because it must call Gemini and the lender sites.
- **Why do RDS and EC2 cost money but Lambda does not (idle)?** RDS and EC2 are machines that are on and billed per hour whether used or not. Lambda is billed per execution. That is why the deploy has a teardown command.
- **What is `serverless.yml`?** A description of the desired AWS setup. Serverless turns it into a CloudFormation template; CloudFormation creates the resources in the right order and deletes them in reverse.
