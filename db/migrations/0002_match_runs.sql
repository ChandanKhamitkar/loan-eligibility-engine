CREATE TABLE match_runs (
    run_id            bigserial PRIMARY KEY,
    upload_id         uuid REFERENCES uploads,
    users_claimed     integer NOT NULL,
    products_claimed  integer NOT NULL,
    naive_pairs       bigint NOT NULL,
    pairs_in_scope    integer NOT NULL,
    pairs_eligible    integer NOT NULL,
    matches_written   integer NOT NULL,
    matches_removed   integer NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
