"""Load demo loan products so matching can run without the crawler. Safe to rerun."""

import json
from pathlib import Path

from src.common.config import get_settings
from src.common.db import connect
from src.common.log import get_logger

SEED_FILE = Path(__file__).resolve().parent.parent / "db" / "seed" / "products.json"
log = get_logger("seed_products")

_UPSERT = """
INSERT INTO loan_products (lender, product_name, rate_min, rate_max, min_income,
                           min_credit_score, min_age, max_age, allowed_employment,
                           residual_criteria)
VALUES (%(lender)s, %(product_name)s, %(rate_min)s, %(rate_max)s, %(min_income)s,
        %(min_credit_score)s, %(min_age)s, %(max_age)s, %(allowed_employment)s,
        %(residual_criteria)s)
ON CONFLICT (lender, product_name) DO UPDATE SET
    rate_min = EXCLUDED.rate_min,
    rate_max = EXCLUDED.rate_max,
    min_income = EXCLUDED.min_income,
    min_credit_score = EXCLUDED.min_credit_score,
    min_age = EXCLUDED.min_age,
    max_age = EXCLUDED.max_age,
    allowed_employment = EXCLUDED.allowed_employment,
    residual_criteria = EXCLUDED.residual_criteria,
    active = true,
    last_seen_at = now(),
    needs_rematch = loan_products.needs_rematch OR (
        (loan_products.min_income, loan_products.min_credit_score, loan_products.min_age,
         loan_products.max_age, loan_products.allowed_employment, loan_products.active)
        IS DISTINCT FROM
        (EXCLUDED.min_income, EXCLUDED.min_credit_score, EXCLUDED.min_age,
         EXCLUDED.max_age, EXCLUDED.allowed_employment, true)
    ),
    updated_at = now()
"""


def main() -> None:
    products = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    with connect(get_settings()) as conn, conn.transaction():
        for product in products:
            conn.execute(_UPSERT, product)
    log.info("seeded %d products", len(products))


if __name__ == "__main__":
    main()
