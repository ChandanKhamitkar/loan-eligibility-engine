from decimal import Decimal

import pytest

from src.ingestion.validators import RowError, validate_row

VALID = {
    "user_id": "b35de23e-755f-4c6a-81d8-f7dd99ce53ef",
    "name": "Dhruv Iyengar",
    "email": "Dhruv.Iyengar@Example.com",
    "monthly_income": "131000",
    "credit_score": "725",
    "employment_status": "self employed",
    "age": "37",
}


def test_valid_row_is_normalised():
    user = validate_row(VALID)
    assert user.email == "dhruv.iyengar@example.com"
    assert user.employment_status == "Self-Employed"
    assert user.monthly_income == Decimal("131000")
    assert user.credit_score == 725


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("user_id", "not-a-uuid", "UUID"),
        ("email", "nope", "malformed"),
        ("monthly_income", "-5", "positive"),
        ("monthly_income", "abc", "not a number"),
        ("credit_score", "1000", "between"),
        ("age", "12", "between"),
        ("employment_status", "Retired", "not recognised"),
        ("name", "  ", "missing"),
    ],
)
def test_invalid_field_is_rejected(field, value, reason):
    with pytest.raises(RowError, match=reason):
        validate_row({**VALID, field: value})


def test_missing_value_is_rejected():
    row = {**VALID, "age": None}
    with pytest.raises(RowError, match="age is missing"):
        validate_row(row)
