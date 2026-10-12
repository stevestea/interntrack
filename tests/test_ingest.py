"""Tests for the ingestion pipeline.

Structure: each test is arrange / act / assert, and the name says what
behaviour is being pinned down. A failing test name should tell you what
broke without reading the body.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.ingest import (
    extract_skills,
    get_or_create_company,
    load_postings,
    parse_bool,
    parse_date,
)
from app.models import Company, Posting, PostingSkill


# --- parse_date ----------------------------------------------------------

def test_parse_date_reads_iso_format():
    assert parse_date("2026-08-14") == date(2026, 8, 14)


def test_parse_date_tolerates_surrounding_whitespace():
    assert parse_date("  2026-08-14  ") == date(2026, 8, 14)


def test_parse_date_returns_none_for_empty_input():
    assert parse_date("") is None
    assert parse_date("   ") is None
    assert parse_date(None) is None


def test_parse_date_returns_none_instead_of_raising_on_garbage():
    """A malformed date must not abort an import of otherwise good rows."""
    assert parse_date("not a date") is None
    assert parse_date("14/08/2026") is None     # wrong format, not wrong data
    assert parse_date("2026-13-45") is None     # impossible month and day


# --- parse_bool ----------------------------------------------------------

def test_parse_bool_accepts_common_truthy_spellings():
    for value in ["true", "TRUE", "True", "yes", "Yes", "1", "y"]:
        assert parse_bool(value) is True, value


def test_parse_bool_defaults_to_false_for_anything_else():
    for value in ["false", "no", "0", "", "maybe", None]:
        assert parse_bool(value) is False, value


# --- extract_skills ------------------------------------------------------

def test_extract_skills_finds_skills_in_description():
    found = extract_skills("We use Python and SQL with Docker.")
    assert "python" in found
    assert "sql" in found
    assert "docker" in found


def test_extract_skills_is_case_insensitive():
    assert extract_skills("PYTHON") == extract_skills("python")


def test_extract_skills_matches_whole_words_only():
    """'r' is a language; it must not match the r inside other words."""
    assert "r" not in extract_skills("Join our team and grow your career")
    assert "r" in extract_skills("Experience with R or Python")


def test_extract_skills_handles_regex_special_characters():
    """'c++' contains regex metacharacters and must still match literally."""
    assert "c++" in extract_skills("Strong C++ background preferred")


def test_extract_skills_deduplicates():
    """A posting that says Python three times yields one skill."""
    found = extract_skills("Python, python, and more PYTHON")
    assert found.count("python") == 1


def test_extract_skills_returns_empty_for_no_description():
    assert extract_skills(None) == []
    assert extract_skills("") == []


# --- get_or_create_company ----------------------------------------------

def test_get_or_create_company_creates_once_and_reuses(session):
    first = get_or_create_company(session, "Datadog")
    second = get_or_create_company(session, "Datadog")
    assert first.id == second.id
    assert session.scalar(select(Company).where(Company.name == "Datadog")) is not None


def test_get_or_create_company_normalizes_whitespace(session):
    """'Datadog ' and 'Datadog' are one employer, not two."""
    a = get_or_create_company(session, "Datadog")
    b = get_or_create_company(session, "  Datadog  ")
    assert a.id == b.id


# --- load_postings -------------------------------------------------------

def test_load_postings_inserts_valid_rows(session, sample_rows):
    stats = load_postings(sample_rows, session)
    assert stats["inserted"] == 2          # third row has no URL
    assert session.query(Posting).count() == 2


def test_load_postings_skips_rows_without_a_url(session, sample_rows):
    stats = load_postings(sample_rows, session)
    assert stats["skipped"] == 1
    assert session.scalar(
        select(Posting).where(Posting.title == "Nowhere Intern")
    ) is None


def test_load_postings_is_idempotent(session, sample_rows):
    """Re-importing the same CSV must be a no-op, not a duplicate storm."""
    load_postings(sample_rows, session)
    second = load_postings(sample_rows, session)
    assert second["inserted"] == 0
    assert second["skipped"] == 3
    assert session.query(Posting).count() == 2


def test_load_postings_degrades_a_bad_date_without_losing_the_row(session, sample_rows):
    load_postings(sample_rows, session)
    posting = session.scalar(
        select(Posting).where(Posting.url == "https://example.com/b")
    )
    assert posting is not None             # the row survived
    assert posting.date_posted is None     # only the date was dropped


def test_load_postings_coerces_types(session, sample_rows):
    load_postings(sample_rows, session)
    remote = session.scalar(select(Posting).where(Posting.url == "https://example.com/b"))
    dated = session.scalar(select(Posting).where(Posting.url == "https://example.com/a"))
    assert remote.remote is True
    assert dated.date_posted == date(2026, 8, 14)


def test_load_postings_stores_extracted_skills(session, sample_rows):
    stats = load_postings(sample_rows, session)
    assert stats["skills"] > 0
    skills = session.scalars(select(PostingSkill.skill)).all()
    assert "python" in skills
    assert "sql" in skills


def test_load_postings_creates_each_company_once(session, sample_rows):
    rows = sample_rows + [dict(sample_rows[0], url="https://example.com/c")]
    load_postings(rows, session)
    assert session.query(Company).filter(Company.name == "Datadog").count() == 1
