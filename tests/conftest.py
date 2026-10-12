"""Shared pytest fixtures.

Every test runs against a fresh in-memory SQLite database. Nothing here
touches data/interntrack.db - tests must never depend on, or damage, real
data. A test that only passes because your dev database happens to hold the
right rows is not a test.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Application, Base, Company, Posting, StatusEvent


@pytest.fixture
def engine():
    """A throwaway in-memory database.

    StaticPool keeps every connection pointed at the SAME in-memory database.
    Without it SQLite hands each new connection a blank one, and tests
    mysteriously see no data.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """An open session on the throwaway database, closed after each test."""
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def sample_rows():
    """Three posting rows shaped as read_postings_csv returns them.

    Deliberately includes one row with a blank date and one with a blank URL,
    so tests exercise the degrade and skip paths, not only the happy one.
    """
    return [
        {
            "company": "Datadog",
            "title": "Software Engineer Intern",
            "location": "New York, NY",
            "remote": "false",
            "url": "https://example.com/a",
            "date_posted": "2026-08-14",
            "source": "linkedin",
            "description": "Python and Go. SQL against Postgres. Git required.",
        },
        {
            "company": "Rackspace",
            "title": "Software Development Intern",
            "location": "San Antonio, TX",
            "remote": "true",
            "url": "https://example.com/b",
            "date_posted": "",                 # missing date -> should degrade to None
            "source": "handshake",
            "description": "Java or Python, REST APIs, SQL, Docker.",
        },
        {
            "company": "Ghost Corp",
            "title": "Nowhere Intern",
            "location": "",
            "remote": "false",
            "url": "",                         # no URL -> should be skipped entirely
            "date_posted": "2026-08-20",
            "source": "",
            "description": "Python.",
        },
    ]


@pytest.fixture
def rejected_application(session):
    """An application that went applied -> interview -> rejected.

    Its CURRENT status is 'rejected', but it passed through 'interview'.
    Used to prove the funnel credits stages reached rather than only the
    final state.
    """
    company = Company(name="Datadog")
    session.add(company)
    session.flush()

    posting = Posting(
        company_id=company.id,
        title="SWE Intern",
        url="https://example.com/applied",
    )
    session.add(posting)
    session.flush()

    application = Application(posting_id=posting.id, status="rejected")
    session.add(application)
    session.flush()

    t0 = datetime(2026, 9, 1, 9, 0)
    session.add_all([
        StatusEvent(application_id=application.id, status="applied", occurred_at=t0),
        StatusEvent(application_id=application.id, status="interview",
                    occurred_at=t0 + timedelta(days=10)),
        StatusEvent(application_id=application.id, status="rejected",
                    occurred_at=t0 + timedelta(days=14)),
    ])
    session.commit()
    return application
