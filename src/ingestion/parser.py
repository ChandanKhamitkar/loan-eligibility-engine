import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from src.ingestion.validators import RowError, UserRow, validate_row

REQUIRED_COLUMNS = (
    "user_id",
    "name",
    "email",
    "monthly_income",
    "credit_score",
    "employment_status",
    "age",
)


class InvalidHeaderError(ValueError):
    pass


@dataclass(frozen=True)
class RowIssue:
    line_no: int
    raw: dict[str, str | None]
    reason: str


@dataclass
class ParsedChunk:
    users: list[UserRow] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    rows_seen: int = 0
    valid_rows: int = 0


def parse_chunks(lines: Iterable[str], chunk_size: int) -> Iterator[ParsedChunk]:
    """Stream CSV lines into validated chunks.

    Within a chunk duplicate user_ids collapse to the last occurrence, because a single
    multi-row upsert cannot touch the same key twice. Across chunks the later upsert wins.
    """
    reader = csv.DictReader(lines)
    reader.fieldnames = _normalised_header(reader.fieldnames)
    chunk = ParsedChunk()
    by_user: dict[str, UserRow] = {}

    for raw in reader:
        chunk.rows_seen += 1
        try:
            user = validate_row(raw)
        except RowError as exc:
            chunk.issues.append(RowIssue(reader.line_num, _printable(raw), str(exc)))
        else:
            chunk.valid_rows += 1
            by_user[user.user_id] = user
        if chunk.rows_seen >= chunk_size:
            chunk.users = list(by_user.values())
            yield chunk
            chunk, by_user = ParsedChunk(), {}

    if chunk.rows_seen:
        chunk.users = list(by_user.values())
        yield chunk


def _normalised_header(fieldnames: list[str] | None) -> list[str]:
    names = [name.strip().lower() for name in fieldnames or []]
    missing = [column for column in REQUIRED_COLUMNS if column not in names]
    if missing:
        raise InvalidHeaderError(f"missing columns: {', '.join(missing)}")
    return names


def _printable(raw: dict) -> dict[str, str | None]:
    return {str(key): value for key, value in raw.items() if key is not None}
