-- Workflow C: pick up to $1 users with unnotified matches (most matches first), each with their best 5 products.
-- Only the top 5 are shown; all of a user's pending matches are marked notified afterwards.
WITH ranked AS (
    SELECT m.user_id, m.product_id,
           row_number() OVER (PARTITION BY m.user_id
                              ORDER BY m.fit_score DESC, m.product_id) AS rn
    FROM matches m
    JOIN loan_products p ON p.product_id = m.product_id AND p.active
    WHERE NOT m.notified
),
picked AS (
    SELECT user_id FROM ranked GROUP BY user_id ORDER BY count(*) DESC, user_id LIMIT $1::int
)
SELECT u.user_id, u.name,
       json_agg(json_build_object(
           'lender', p.lender, 'product_name', p.product_name,
           'rate_min', p.rate_min, 'rate_max', p.rate_max) ORDER BY r.rn) AS products
FROM picked pk
JOIN users u ON u.user_id = pk.user_id
JOIN ranked r ON r.user_id = u.user_id AND r.rn <= 5
JOIN loan_products p ON p.product_id = r.product_id
GROUP BY u.user_id, u.name
ORDER BY u.user_id;
