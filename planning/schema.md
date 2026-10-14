# Database Schema

Postgres. One server, two databases: `app` (below) and `n8n` (n8n internals, untouched by us). Migrations are plain numbered `.sql` files in `db/migrations/`. No ORM.

## Tables

5 core + 2 optional.

### uploads
Tracks each CSV batch; drives UI status.

| Column | Type | Notes |
|---|---|---|
| upload_id | uuid PK | generated at presign time |
| object_key | text not null | storage key |
| filename | text not null | |
| status | text not null | `uploaded, processing, processed, matching, matched, notified, failed`; CHECK |
| rows_total / rows_ok / rows_rejected | int not null default 0 | |
| error | text | set when `failed` |
| created_at / updated_at | timestamptz not null default now() | |

### users

| Column | Type | Notes |
|---|---|---|
| user_id | uuid PK | the identity; **email is not unique** (2,403 shared in sample) |
| name | text not null | |
| email | text not null | |
| monthly_income | numeric(12,2) not null | CHECK > 0 |
| credit_score | smallint not null | CHECK 300-900 |
| employment_status | text not null | CHECK in (`Salaried`,`Self-Employed`,`Business`); normalized on ingest |
| age | smallint not null | CHECK 18-100 |
| needs_match | boolean not null default true | see semantics |
| last_upload_id | uuid FK → uploads | |
| created_at / updated_at | timestamptz not null default now() | |

### crawl_sources
Site list (config) and the latest snapshot in one table.

| Column | Type | Notes |
|---|---|---|
| source_id | serial PK | |
| lender | text not null | |
| url | text not null unique | |
| enabled | boolean not null default true | |
| content_hash | text | hash of cleaned text |
| cleaned_text | text | latest snapshot only |
| last_fetched_at / last_changed_at | timestamptz | |
| last_status | text | `ok`, `fetch_failed`, `extract_failed` |

### loan_products

| Column | Type | Notes |
|---|---|---|
| product_id | serial PK | |
| source_id | int FK → crawl_sources | |
| lender, product_name | text not null | UNIQUE (lender, product_name) |
| rate_min / rate_max | numeric(5,2) | nullable |
| min_income | numeric(12,2) | null = no constraint |
| min_credit_score | smallint | null = no constraint |
| min_age / max_age | smallint | null = no constraint |
| allowed_employment | text[] | null = any |
| residual_criteria | text | criteria the schema couldn't capture |
| source_url | text | |
| active | boolean not null default true | |
| last_seen_at | timestamptz not null | |
| needs_rematch | boolean not null default true | see semantics |
| created_at / updated_at | timestamptz not null default now() | |

CHECKs: `rate_min <= rate_max`, `min_age <= max_age`.

### matches

| Column | Type | Notes |
|---|---|---|
| user_id | uuid FK → users ON DELETE CASCADE | |
| product_id | int FK → loan_products ON DELETE CASCADE | |
| stage | smallint not null | funnel stage that produced it |
| fit_score | numeric | used for ranking (e.g. lower rate = better) |
| notified | boolean not null default false | |
| notified_at | timestamptz | |
| created_at | timestamptz not null default now() | |
| | PK (user_id, product_id) | makes reruns idempotent |

### upload_errors (optional)
`upload_id` FK, `line_no` int, `raw` jsonb, `reason` text. Per-row rejection reasons for the UI.

### llm_cache (optional)
`cache_key` text PK (hash of criteria + user bucket), `response` jsonb, `created_at`. Only if stage 3 is built.

## Indexes

| Index | Purpose |
|---|---|
| `users (needs_match) WHERE needs_match` | cheap "what needs matching" scan |
| `loan_products (needs_rematch) WHERE needs_rematch` | same for products |
| `matches (user_id) WHERE NOT notified` | Workflow C lookup |
| `matches (product_id)` | clear stale matches per product |

Funnel is a join over a few dozen products, so no further indexes on criteria columns.

## Flag semantics

| Flag | Set to true when | Cleared when |
|---|---|---|
| `users.needs_match` | new user, or upsert changed any of income, score, employment, age | Workflow B claims the user |
| `loan_products.needs_rematch` | new product, or extracted criteria changed | Workflow B claims the product |
| `matches.notified` | never (default false) | Workflow C sends successfully |

Name and email changes do **not** set `needs_match` (no effect on eligibility).

## Key patterns

**User upsert (latest wins, flag only on real change).** Dedupe within each chunk first (keep last), then:

```sql
INSERT INTO users (user_id, name, email, monthly_income, credit_score, employment_status, age, last_upload_id)
VALUES (...)
ON CONFLICT (user_id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    monthly_income = EXCLUDED.monthly_income,
    credit_score = EXCLUDED.credit_score,
    employment_status = EXCLUDED.employment_status,
    age = EXCLUDED.age,
    last_upload_id = EXCLUDED.last_upload_id,
    needs_match = users.needs_match OR (
        (users.monthly_income, users.credit_score, users.employment_status, users.age)
        IS DISTINCT FROM
        (EXCLUDED.monthly_income, EXCLUDED.credit_score, EXCLUDED.employment_status, EXCLUDED.age)),
    updated_at = now();
```

**Match scope.** A (user, product) pair is evaluated if the user is flagged **or** the product is flagged, i.e. flagged users × all active products ∪ all users × flagged products.

**Funnel stage 1 (illustrative):**

```sql
SELECT u.user_id, p.product_id
FROM users u
JOIN loan_products p ON p.active
WHERE (u.needs_match OR p.needs_rematch)
  AND (p.min_income       IS NULL OR u.monthly_income >= p.min_income)
  AND (p.min_credit_score IS NULL OR u.credit_score   >= p.min_credit_score)
  AND (p.min_age          IS NULL OR u.age            >= p.min_age)
  AND (p.max_age          IS NULL OR u.age            <= p.max_age)
  AND (p.allowed_employment IS NULL OR u.employment_status = ANY (p.allowed_employment));
```

**Claim-and-match is atomic.** Workflow B flips the flags with `UPDATE ... RETURNING` inside the same statement/transaction that deletes stale unnotified matches in scope and inserts new ones (`ON CONFLICT DO NOTHING`, so already-notified pairs are never re-sent). Rows flagged during a run are not lost or half-processed.

**Notify safety.** C marks `notified = true` per user only after a successful send; a failed send stays `false` and is retried next run. Join to `loan_products.active` at send time so deactivated products are not emailed.
