# Planning

Loan Eligibility Engine, a take-home for ClickPe. A pipeline that ingests a user CSV, crawls loan products from public sites, matches users to eligible products, and emails them. Lambda/S3 handle ingestion, Postgres stores data, and n8n orchestrates the business logic (crawl, match, notify). Built local-first in Docker Compose, then deployed to AWS.

| File | Contents |
|---|---|
| [decisions.md](decisions.md) | Assessment essentials, final stack, per-workflow design, matching funnel, edge cases, open items. Source of truth. |
| [architecture.md](architecture.md) | V1 (local) HLD, final (AWS) HLD, flow diagrams for ingestion, A, B, C, status lifecycle |
| [schema.md](schema.md) | Tables, columns, constraints, indexes, flag semantics, key SQL patterns |
| [directory-structure.md](directory-structure.md) | Repo layout and where things go |
| [coding-standards.md](coding-standards.md) | Python, SQL, n8n and config conventions |
| The Loan Eligibility Engine (Engineering Intern)-clickpe.docx | Original assessment brief |
| [../data/users.csv](../data/users.csv) | Sample dataset (10,000 users) |

**Using as context:** pass `decisions.md` plus whichever of the others the task touches. The brief is only for re-checking requirements.
