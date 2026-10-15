import pytest

from src.ingestion.parser import InvalidHeaderError, parse_chunks

HEADER = "user_id,name,email,monthly_income,credit_score,employment_status,age\n"
ID_A = "b35de23e-755f-4c6a-81d8-f7dd99ce53ef"
ID_B = "77fce4da-b901-4b27-b1bb-01989567b98b"


def row(user_id, income="50000", score="700"):
    return f"{user_id},Name,n@example.com,{income},{score},Salaried,30\n"


def test_chunks_respect_size():
    lines = [HEADER, row(ID_A), row(ID_B), row(ID_A, income="60000")]
    chunks = list(parse_chunks(lines, chunk_size=2))
    assert [c.rows_seen for c in chunks] == [2, 1]


def test_duplicate_in_chunk_keeps_last():
    lines = [HEADER, row(ID_A, income="50000"), row(ID_A, income="90000")]
    (chunk,) = parse_chunks(lines, chunk_size=10)
    assert len(chunk.users) == 1
    assert chunk.users[0].monthly_income == 90000
    assert chunk.valid_rows == 2


def test_bad_rows_become_issues_with_line_numbers():
    lines = [HEADER, row(ID_A), row("bad-id")]
    (chunk,) = parse_chunks(lines, chunk_size=10)
    assert chunk.valid_rows == 1
    assert [(i.line_no, "UUID" in i.reason) for i in chunk.issues] == [(3, True)]


def test_header_is_case_insensitive_and_extra_columns_ignored():
    header = "User_ID, Name,EMAIL,monthly_income,credit_score,employment_status,age,extra\n"
    lines = [header, row(ID_A).strip() + ",x\n"]
    (chunk,) = parse_chunks(lines, chunk_size=10)
    assert chunk.valid_rows == 1


def test_missing_column_raises():
    with pytest.raises(InvalidHeaderError, match="age"):
        list(
            parse_chunks(["user_id,name,email,monthly_income,credit_score,employment_status\n"], 10)
        )


def test_empty_file_yields_nothing():
    assert list(parse_chunks([HEADER], chunk_size=10)) == []
