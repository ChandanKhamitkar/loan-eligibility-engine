CREATE TABLE uploads (
    upload_id      uuid PRIMARY KEY,
    object_key     text NOT NULL,
    filename       text NOT NULL,
    status         text NOT NULL DEFAULT 'uploaded'
        CHECK (status IN ('uploaded', 'processing', 'processed', 'matching', 'matched', 'notified', 'failed')),
    rows_total     integer NOT NULL DEFAULT 0,
    rows_ok        integer NOT NULL DEFAULT 0,
    rows_rejected  integer NOT NULL DEFAULT 0,
    error          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE upload_errors (
    upload_id  uuid NOT NULL REFERENCES uploads ON DELETE CASCADE,
    line_no    integer NOT NULL,
    raw        jsonb NOT NULL,
    reason     text NOT NULL
);
CREATE INDEX upload_errors_upload_idx ON upload_errors (upload_id);

CREATE TABLE users (
    user_id            uuid PRIMARY KEY,
    name               text NOT NULL,
    email              text NOT NULL,
    monthly_income     numeric(12, 2) NOT NULL CHECK (monthly_income > 0),
    credit_score       smallint NOT NULL CHECK (credit_score BETWEEN 300 AND 900),
    employment_status  text NOT NULL
        CHECK (employment_status IN ('Salaried', 'Self-Employed', 'Business')),
    age                smallint NOT NULL CHECK (age BETWEEN 18 AND 100),
    needs_match        boolean NOT NULL DEFAULT true,
    last_upload_id     uuid REFERENCES uploads,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX users_needs_match_idx ON users (needs_match) WHERE needs_match;

CREATE TABLE crawl_sources (
    source_id        serial PRIMARY KEY,
    lender           text NOT NULL,
    url              text NOT NULL UNIQUE,
    enabled          boolean NOT NULL DEFAULT true,
    content_hash     text,
    cleaned_text     text,
    last_fetched_at  timestamptz,
    last_changed_at  timestamptz,
    last_status      text
);

CREATE TABLE loan_products (
    product_id          serial PRIMARY KEY,
    source_id           integer REFERENCES crawl_sources,
    lender              text NOT NULL,
    product_name        text NOT NULL,
    rate_min            numeric(5, 2),
    rate_max            numeric(5, 2),
    min_income          numeric(12, 2),
    min_credit_score    smallint,
    min_age             smallint,
    max_age             smallint,
    allowed_employment  text[],
    residual_criteria   text,
    source_url          text,
    active              boolean NOT NULL DEFAULT true,
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    needs_rematch       boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lender, product_name),
    CHECK (rate_min IS NULL OR rate_max IS NULL OR rate_min <= rate_max),
    CHECK (min_age IS NULL OR max_age IS NULL OR min_age <= max_age)
);
CREATE INDEX loan_products_needs_rematch_idx ON loan_products (needs_rematch) WHERE needs_rematch;

CREATE TABLE matches (
    user_id      uuid NOT NULL REFERENCES users ON DELETE CASCADE,
    product_id   integer NOT NULL REFERENCES loan_products ON DELETE CASCADE,
    stage        smallint NOT NULL,
    fit_score    numeric,
    notified     boolean NOT NULL DEFAULT false,
    notified_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, product_id)
);
CREATE INDEX matches_pending_idx ON matches (user_id) WHERE NOT notified;
CREATE INDEX matches_product_idx ON matches (product_id);
