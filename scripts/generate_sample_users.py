"""Generate synthetic user CSVs for trying the pipeline without the assessment dataset.

Usage:
    python scripts/generate_sample_users.py                       # 10,000 users -> data/users.csv
    python scripts/generate_sample_users.py --rows 20 --edge-cases --out data/demo_users.csv

Output is deterministic for a given --seed. Emails always use example.com.
--edge-cases appends three rows: a repeated user_id with a new income (latest wins),
an invalid user_id and an out-of-range credit score (both rejected by the pipeline).
"""

import argparse
import csv
import random
import uuid
from pathlib import Path

HEADER = ["user_id", "name", "email", "monthly_income", "credit_score", "employment_status", "age"]
FIRST_NAMES = [
    "Aarav", "Aditya", "Ananya", "Diya", "Dhruv", "Isha", "Ishaan", "Kabir", "Meera", "Neha",
    "Rohan", "Saanvi", "Sana", "Tara", "Vivaan", "Zoya",
]  # fmt: skip
LAST_NAMES = [
    "Agarwal", "Chopra", "Desai", "Gupta", "Iyer", "Joshi", "Kapoor", "Khan", "Pandey", "Rao",
    "Reddy", "Roy", "Sharma", "Soni", "Thakur", "Trivedi",
]  # fmt: skip
EMPLOYMENT = ["Salaried", "Self-Employed", "Business"]


def make_user(rng: random.Random) -> list[str]:
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    return [
        str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        f"{first} {last}",
        f"{first}.{last}@example.com".lower(),
        str(rng.randrange(25_000, 150_001, 1_000)),
        str(rng.randrange(650, 801, 5)),
        rng.choice(EMPLOYMENT),
        str(rng.randint(22, 50)),
    ]


def edge_case_rows(first_user: list[str]) -> list[list[str]]:
    raised_income = [*first_user]
    raised_income[3] = str(int(first_user[3]) + 25_000)
    return [
        raised_income,
        ["not-a-uuid", "Bad Id", "bad.id@example.com", "50000", "700", "Salaried", "30"],
        [
            "11111111-2222-4333-8444-555555555555",
            "Low Score",
            "low.score@example.com",
            "50000",
            "1000",
            "Salaried",
            "30",
        ],
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--out", type=Path, default=Path("data/users.csv"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--edge-cases", action="store_true")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows = [make_user(rng) for _ in range(args.rows)]
    if args.edge_cases and rows:
        rows += edge_case_rows(rows[0])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
