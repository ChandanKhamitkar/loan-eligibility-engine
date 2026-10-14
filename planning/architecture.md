# Architecture

Diagrams are Mermaid (render on GitHub and in VS Code). Design rationale lives in [decisions.md](decisions.md); tables in [schema.md](schema.md).

## 1. V1 HLD: local (build target first)

Everything runs in Docker Compose on one machine.

```mermaid
flowchart LR
    UI["Browser UI<br/>static HTML"] -->|"1 get upload URL"| API["Local API adapter<br/>Flask, wraps handlers"]
    API -->|"presigned URL"| UI
    UI -->|"2 PUT csv"| OBJ[("Object storage<br/>MinIO")]
    OBJ -->|"3 ObjectCreated notification"| API
    API -->|"4 parse + upsert"| PG[("Postgres<br/>app DB")]
    API -->|"5 webhook: upload_id"| N8N["n8n<br/>Workflows A B C"]
    N8N <-->|"SQL"| PG
    N8N -->|"crawl daily"| WEB["Public loan sites"]
    N8N -->|"extract JSON"| LLM["Gemini API"]
    N8N -->|"send mail"| SMTP["Gmail SMTP"]
    UI -.->|"poll status"| API
```

| Component | Role |
|---|---|
| Local API adapter | Thin Flask app calling the same handler functions Lambda will run (presign, process CSV, status). Fallback if MinIO is unusable: it receives the file itself. |
| Postgres | One server, two databases: `app` (our tables) and `n8n` (n8n internals) |
| n8n | All business logic: A crawls, B matches, C notifies |

## 2. Final HLD: AWS

Same logic; adapters replaced by AWS services.

```mermaid
flowchart LR
    UI["Browser UI<br/>S3 static site or local"] -->|"1 request upload"| APIGW["API Gateway"]
    APIGW --> L1["Lambda<br/>get_upload_url"]
    L1 -->|"presigned URL"| UI
    UI -->|"2 PUT csv"| S3[("S3 bucket")]
    S3 -->|"3 ObjectCreated"| L2["Lambda<br/>process_csv"]
    L2 -->|"4 validate + upsert"| RDS[("RDS Postgres")]
    L2 -->|"5 webhook + secret"| N8N["n8n in Docker<br/>EC2 or local + tunnel"]
    N8N <-->|"SQL"| RDS
    N8N -->|"crawl"| WEB["Public loan sites"]
    N8N -->|"extract"| LLM["Gemini API"]
    N8N -->|"send"| SES["AWS SES"]
    UI -.->|"poll status"| APIGW
    APIGW --> L3["Lambda<br/>get_status"]
    L3 --> RDS
```

Open for this phase: where n8n runs (EC2 vs local + tunnel) and how Lambda/n8n reach RDS without a NAT gateway (public RDS restricted by security group, Lambda outside the VPC).

## 3. Flow: ingestion

```mermaid
sequenceDiagram
    participant U as UI
    participant A as get_upload_url
    participant S as Object storage
    participant P as process_csv
    participant D as Postgres
    participant N as n8n Workflow B

    U->>A: POST /uploads (filename)
    A->>D: insert uploads (status=uploaded)
    A-->>U: upload_id + presigned PUT URL
    U->>S: PUT file directly
    S->>P: ObjectCreated event
    P->>D: status=processing
    loop each chunk
        P->>P: validate rows, dedupe in chunk
        P->>D: upsert users (needs_match only if changed)
    end
    P->>D: status=processed, row counts
    P->>N: POST webhook (upload_id, secret header)
    U->>A: GET /uploads/upload_id (poll)
    A-->>U: status + counts
```

## 4. Flow: Workflow A (product discovery)

```mermaid
flowchart TD
    T["Schedule: daily"] --> S["Read enabled crawl_sources"]
    S --> L{"Next source?"}
    L -->|yes| H["HTTP GET page"]
    H -->|fail| F["Record last_status, continue"] --> L
    H --> C["Clean HTML to text<br/>keep tables"]
    C --> HS["Hash cleaned text"]
    HS --> Q{"Hash changed?"}
    Q -->|no| U1["Update last_fetched_at"] --> L
    Q -->|yes| G["Gemini: extract products<br/>fixed JSON schema"]
    G --> V{"Valid JSON?"}
    V -->|no| F
    V -->|yes| UP["Upsert loan_products<br/>changed criteria set needs_rematch"]
    UP --> SV["Save hash + cleaned text"] --> L
    L -->|done| I["Mark products unseen for N days inactive"]
```

## 5. Flow: Workflow B (matching)

```mermaid
flowchart TD
    W["Webhook trigger"] --> AU{"Secret header valid?"}
    AU -->|no| R["401 reject"]
    AU -->|yes| M1["uploads.status = matching"]
    M1 --> FN["One transaction:<br/>claim flagged users and products,<br/>clear stale unnotified matches,<br/>run funnel, insert matches"]
    FN --> Q{"Products with residual_criteria<br/>and candidates?"}
    Q -->|yes| LLM["Optional: bucketed LLM check<br/>cached"]
    Q -->|no| M2
    LLM --> M2["uploads.status = matched"]
    M2 --> CALL["Call Workflow C"]
```

Funnel stages (details in decisions.md): 0 scope (flagged only) → 1 SQL hard-rule join → 2 rank and cap top N per user → 3 optional bucketed LLM. The LLM never sees the DB; n8n passes only the needed fields.

## 6. Flow: Workflow C (notification)

```mermaid
flowchart TD
    S["Called by B"] --> Q["Select users with notified=false matches<br/>aggregate products per user"]
    Q --> LIM["Apply NOTIFY_LIMIT in demo mode"]
    LIM --> L{"Next user?"}
    L -->|yes| B["Build email body<br/>name + product list"]
    B --> RM["Remap recipient to test alias"]
    RM --> SEND["Send: Gmail SMTP, later SES"]
    SEND -->|ok| MK["matches.notified = true"] --> D["Short delay"] --> L
    SEND -->|fail| LOG["Log, leave notified=false"] --> L
    L -->|done| ST["uploads.status = notified"]
```

## 7. Upload status lifecycle

```mermaid
stateDiagram-v2
    [*] --> uploaded
    uploaded --> processing: object created
    processing --> processed: rows upserted
    processing --> failed: parse or DB error
    processed --> matching: webhook received
    matching --> matched: matches stored
    matching --> failed: workflow error
    matched --> notified: emails sent
```

## 8. Trust boundaries and secrets

| Boundary | Protection |
|---|---|
| Processor → n8n webhook | Shared-secret header |
| n8n → Postgres, SMTP/SES, Gemini | Credentials in n8n store only |
| Upload | Short-lived presigned URL; size and content-type limits |
| Prompts | No emails or names sent to the LLM |
| Email | Recipients always remapped to test aliases |
