"""Reading postings in from outside the app.

Ingestion is deliberately separated from storage. Anything that can produce
a list of normalized row-dicts can feed `load_postings`. CSV is the primary
path; a scraper can be added later without touching the database code, and
if that scraper breaks the CSV path still works.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session, init_db
from app.models import Company, Posting, PostingSkill

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Skills we look for in posting descriptions. Lowercase; matched as whole
# words so "r" doesn't match every letter r, and "go" doesn't match "going".
#
# This is a keyword list, not machine learning. That is a deliberate choice:
# it is transparent, debuggable, and good enough when the vocabulary of tech
# job postings is this stable. The cost is that it only finds skills that
# are on the list.
SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "sql", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis",
    "react", "angular", "vue", "node", "django", "flask", "spring", "rails",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "linux",
    "git", "ci/cd", "jenkins", "github actions",
    "pandas", "numpy", "spark", "hadoop", "tableau", "power bi", "excel",
    "machine learning", "tensorflow", "pytorch",
    "rest", "graphql", "api", "agile", "scrum", "unit testing", "testing",
    "data structures", "algorithms", "statistics",
]


def read_postings_csv(path: str | Path) -> list[dict[str, str]]:
    """Read a CSV of postings and return one dict per row.

    newline="" matters: the csv module does its own line-ending handling,
    and without it a quoted field containing a newline breaks on Windows.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def parse_date(value: str | None) -> date | None:
    """Turn a YYYY-MM-DD string into a date, or None if it is missing/bad.

    Returning None rather than raising is the right call here: one malformed
    date should not abort an import of 200 good rows. The posting still has
    value without knowing exactly when it was listed.
    """
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_bool(value: str | None) -> bool:
    """CSVs carry text, so 'true'/'yes'/'1' all have to mean True."""
    return str(value).strip().lower() in {"true", "yes", "1", "y"}


def extract_skills(description: str | None) -> list[str]:
    """Find known skill keywords in a posting description.

    Whole-word matching via regex word boundaries, so "r" matches the
    language R but not the r inside "your". re.escape handles keywords with
    regex-special characters like "c++".

    Returns a sorted list with no duplicates - a posting that says "Python"
    three times still produces one skill.
    """
    if not description:
        return []
    text = description.lower()
    found = set()
    for keyword in SKILL_KEYWORDS:
        pattern = r"(?<![\w+#])" + re.escape(keyword) + r"(?![\w+#])"
        if re.search(pattern, text):
            found.add(keyword)
    return sorted(found)


def get_or_create_company(session: Session, name: str) -> Company:
    """Return the Company with this name, creating it if it does not exist.

    This is why `companies` is its own table. Without it, "Datadog" and
    "Datadog " would be two different employers and every per-company
    statistic would silently split in half.

    session.flush() pushes the INSERT so the new row gets its id, without
    committing the surrounding transaction - the caller still decides
    whether the whole import succeeds or rolls back.
    """
    name = name.strip()
    company = session.scalar(select(Company).where(Company.name == name))
    if company is None:
        company = Company(name=name)
        session.add(company)
        session.flush()
    return company


def load_postings(rows: list[dict[str, str]], session: Session) -> dict[str, int]:
    """Load normalized rows into the database. Returns a summary of what happened.

    Deduplication is by URL. We check in Python to skip cleanly and report a
    count, but `postings.url` also carries a UNIQUE constraint - the database
    is the real guarantee. The Python check is a courtesy, not the defense.
    """
    stats = {"inserted": 0, "skipped": 0, "skills": 0}

    for row in rows:
        url = (row.get("url") or "").strip()
        if not url:
            stats["skipped"] += 1
            continue

        existing = session.scalar(select(Posting).where(Posting.url == url))
        if existing is not None:
            stats["skipped"] += 1
            continue

        company = get_or_create_company(session, row.get("company", "Unknown"))
        description = (row.get("description") or "").strip() or None

        posting = Posting(
            company_id=company.id,
            title=(row.get("title") or "").strip(),
            location=(row.get("location") or "").strip() or None,
            remote=parse_bool(row.get("remote")),
            url=url,
            description=description,
            date_posted=parse_date(row.get("date_posted")),
            source=(row.get("source") or "").strip() or None,
        )
        session.add(posting)
        session.flush()

        for skill in extract_skills(description):
            session.add(PostingSkill(posting_id=posting.id, skill=skill))
            stats["skills"] += 1

        stats["inserted"] += 1

    session.commit()
    return stats


def import_csv(path: str | Path) -> dict[str, int]:
    """Read a CSV and load it. The whole pipeline in one call."""
    init_db()
    rows = read_postings_csv(path)
    session = get_session()
    try:
        return load_postings(rows, session)
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    csv_path = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ROOT / "data" / "sample_postings.csv"
    result = import_csv(csv_path)
    print(f"Imported from {csv_path}")
    print(f"  inserted: {result['inserted']}")
    print(f"  skipped (duplicate or no URL): {result['skipped']}")
    print(f"  skill tags created: {result['skills']}")
