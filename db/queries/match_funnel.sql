-- Workflow B: claim flagged users/products, run the hard-rule funnel, store matches.
-- One statement = one transaction, so a crash cannot lose a claimed user.
-- $1 = upload_id that triggered the run (for the run log only).
WITH claimed_users AS (
    UPDATE users SET needs_match = false
    WHERE needs_match
    RETURNING user_id
),
claimed_products AS (
    UPDATE loan_products SET needs_rematch = false
    WHERE needs_rematch
    RETURNING product_id
),
-- Stage 0: only flagged users, or any user against flagged products
scope AS (
    SELECT u.user_id, u.monthly_income, u.credit_score, u.age, u.employment_status,
           p.product_id, p.min_income, p.min_credit_score, p.min_age, p.max_age,
           p.allowed_employment, p.rate_min, p.rate_max
    FROM users u
    CROSS JOIN loan_products p
    WHERE p.active
      AND (u.user_id IN (SELECT user_id FROM claimed_users)
           OR p.product_id IN (SELECT product_id FROM claimed_products))
),
-- Stage 1: hard rules. A null criterion means "no constraint".
eligible AS (
    SELECT user_id, product_id,
           100 - COALESCE(rate_min, rate_max, 30) AS fit_score
    FROM scope
    WHERE (min_income IS NULL OR monthly_income >= min_income)
      AND (min_credit_score IS NULL OR credit_score >= min_credit_score)
      AND (min_age IS NULL OR age >= min_age)
      AND (max_age IS NULL OR age <= max_age)
      AND (allowed_employment IS NULL OR employment_status = ANY (allowed_employment))
),
-- Drop unnotified matches in scope that are no longer eligible; notified ones stay as history
removed AS (
    DELETE FROM matches m
    WHERE NOT m.notified
      AND (m.user_id IN (SELECT user_id FROM claimed_users)
           OR m.product_id IN (SELECT product_id FROM claimed_products))
      AND NOT EXISTS (
          SELECT 1 FROM eligible e
          WHERE e.user_id = m.user_id AND e.product_id = m.product_id)
    RETURNING 1
),
written AS (
    INSERT INTO matches (user_id, product_id, stage, fit_score)
    SELECT user_id, product_id, 1, fit_score FROM eligible
    ON CONFLICT (user_id, product_id) DO UPDATE
        SET stage = EXCLUDED.stage, fit_score = EXCLUDED.fit_score
        WHERE NOT matches.notified
    RETURNING 1
)
INSERT INTO match_runs (upload_id, users_claimed, products_claimed, naive_pairs,
                        pairs_in_scope, pairs_eligible, matches_written, matches_removed)
SELECT $1::uuid,
       (SELECT count(*) FROM claimed_users),
       (SELECT count(*) FROM claimed_products),
       (SELECT count(*) FROM users) * (SELECT count(*) FROM loan_products WHERE active),
       (SELECT count(*) FROM scope),
       (SELECT count(*) FROM eligible),
       (SELECT count(*) FROM written),
       (SELECT count(*) FROM removed)
RETURNING *;
