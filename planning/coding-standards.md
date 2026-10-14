# Coding Standards

## Python
- Python 3.12, type hints on every function signature.
- Format and lint with `ruff` (format + check). Line length 100. No wildcard imports.
- Small functions, one job each. Pure logic (parsing, validation, normalization) kept separate from I/O (DB, storage, HTTP) so it can be unit-tested without mocks.
- Lambda handlers are thin: parse the event, call a function, return the response. Business logic never lives in the handler.
- Dependencies: `boto3`, `psycopg[binary]` 3, stdlib `csv`. Flask only in the local adapter. No pandas, no ORM.

## Comments and docstrings
- Code explains *what*; comments explain *why* (a constraint, a trade-off, a non-obvious decision).
- Docstring only on public functions with non-obvious behavior; one or two lines.
- No banner comments, no commented-out code, no restating the line below.

## Naming
- `snake_case` for functions/variables/files, `PascalCase` for classes, `UPPER_SNAKE` for constants.
- Names say what a thing is: `parse_rows`, `upsert_users`, not `process`, `handle`, `do_stuff`.

## Config and secrets
- All config from environment variables, read and validated once at startup in one module.
- `.env.example` is committed; `.env` is gitignored. No secrets in code, workflow JSON, or logs.
- n8n credentials live in n8n's store; exported workflow JSON must contain none.

## Database
- Parameterized SQL only; never build SQL from strings with user data.
- Bulk work is set-based (chunked multi-row upsert or `COPY` to staging), never row-by-row in a loop.
- Schema changes only via numbered migration files; migrations are idempotent where practical.

## Errors and logging
- Validate at the boundary (CSV rows, webhook payload, LLM JSON); inside, trust typed data.
- A bad row is rejected and counted, not fatal. Unexpected errors fail the upload with a message in `uploads.error`.
- Use `logging` with structured context (`upload_id`), never `print`. Log counts and IDs, not PII.
- Catch specific exceptions; no bare `except`.

## n8n workflows
- Descriptive node names (`Hash cleaned text`, not `Code1`). One purpose per node.
- Prefer SQL for set-based work over looping items in n8n.
- Every workflow has error handling (error branch or shared error workflow).
- Exported JSON is committed with credentials stripped; list required credentials in the setup docs.

## Git and testing
- Small commits with imperative messages (`Add CSV row validator`).
- Tests for the parts that can silently be wrong: row validation/normalization, chunk dedupe, upsert flag behavior, funnel SQL on a tiny fixture.
- No test for trivial glue.
