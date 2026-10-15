import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

EMPLOYMENT_ALIASES = {
    "salaried": "Salaried",
    "self-employed": "Self-Employed",
    "self employed": "Self-Employed",
    "selfemployed": "Self-Employed",
    "business": "Business",
}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_CREDIT_SCORE, MAX_CREDIT_SCORE = 300, 900
MIN_AGE, MAX_AGE = 18, 100


class RowError(ValueError):
    """A CSV row failed validation; the message is stored as the rejection reason."""


@dataclass(frozen=True)
class UserRow:
    user_id: str
    name: str
    email: str
    monthly_income: Decimal
    credit_score: int
    employment_status: str
    age: int


def validate_row(raw: dict[str, str | None]) -> UserRow:
    return UserRow(
        user_id=_parse_user_id(_field(raw, "user_id")),
        name=_require(_field(raw, "name"), "name"),
        email=_parse_email(_field(raw, "email")),
        monthly_income=_parse_income(_field(raw, "monthly_income")),
        credit_score=_parse_int(
            _field(raw, "credit_score"), "credit_score", MIN_CREDIT_SCORE, MAX_CREDIT_SCORE
        ),
        employment_status=_parse_employment(_field(raw, "employment_status")),
        age=_parse_int(_field(raw, "age"), "age", MIN_AGE, MAX_AGE),
    )


def _field(raw: dict[str, str | None], key: str) -> str:
    return (raw.get(key) or "").strip()


def _require(value: str, name: str) -> str:
    if not value:
        raise RowError(f"{name} is missing")
    return value


def _parse_user_id(value: str) -> str:
    try:
        return str(uuid.UUID(_require(value, "user_id")))
    except ValueError:
        raise RowError("user_id is not a valid UUID") from None


def _parse_email(value: str) -> str:
    value = _require(value, "email").lower()
    if not _EMAIL_RE.match(value):
        raise RowError("email is malformed")
    return value


def _parse_income(value: str) -> Decimal:
    try:
        income = Decimal(_require(value, "monthly_income"))
    except InvalidOperation:
        raise RowError("monthly_income is not a number") from None
    if not income.is_finite() or income <= 0:
        raise RowError("monthly_income must be positive")
    return income


def _parse_int(value: str, name: str, low: int, high: int) -> int:
    try:
        number = int(Decimal(_require(value, name)))
    except InvalidOperation:
        raise RowError(f"{name} is not a number") from None
    if not low <= number <= high:
        raise RowError(f"{name} must be between {low} and {high}")
    return number


def _parse_employment(value: str) -> str:
    status = EMPLOYMENT_ALIASES.get(_require(value, "employment_status").lower())
    if status is None:
        raise RowError(f"employment_status '{value}' is not recognised")
    return status
