"""Tests for the Flask routes.

These are smoke tests, not unit tests: they check that each page builds and
returns the right status and content, which catches the large majority of
template and query breakages. They do not assert on styling.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

import app.db as db_module
from app.ingest import load_postings
from app.models import Application, StatusEvent


@pytest.fixture
def client(engine, monkeypatch, sample_rows):
    """A Flask test client wired to the in-memory database.

    monkeypatch swaps the module-level engine and session factory before the
    app is created, so every route reads the throwaway database instead of
    data/interntrack.db. The application-factory pattern is what makes this
    possible - a module-level app built at import time could not be redirected.
    """
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)

    from app.web import create_app

    flask_app = create_app()
    flask_app.config["TESTING"] = True

    seed = TestSession()
    load_postings(sample_rows, seed)
    seed.close()

    with flask_app.test_client() as c:
        yield c


def test_index_lists_postings(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Software Engineer Intern" in response.data
    assert b"Datadog" in response.data


def test_index_search_filters_by_title(client):
    response = client.get("/?q=Development")
    assert b"Software Development Intern" in response.data
    assert b"Software Engineer Intern" not in response.data


def test_index_remote_filter(client):
    response = client.get("/?remote=1")
    assert b"Rackspace" in response.data      # the remote one
    assert b"Datadog" not in response.data


def test_posting_detail_shows_skills(client):
    response = client.get("/postings/1")
    assert response.status_code == 200
    assert b"python" in response.data


def test_posting_detail_404s_for_unknown_id(client):
    assert client.get("/postings/9999").status_code == 404


def test_dashboard_renders(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Skills in demand" in response.data
    assert b"Application funnel" in response.data


def test_apply_creates_application_and_opening_event(client, engine):
    response = client.post("/postings/1/apply", follow_redirects=True)
    assert response.status_code == 200

    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        assert s.query(Application).count() == 1
        # The event log must start the moment the application does.
        assert s.query(StatusEvent).count() == 1
        assert s.query(StatusEvent).first().status == "applied"
    finally:
        s.close()


def test_apply_twice_does_not_create_a_second_application(client, engine):
    client.post("/postings/1/apply", follow_redirects=True)
    client.post("/postings/1/apply", follow_redirects=True)

    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        assert s.query(Application).count() == 1
    finally:
        s.close()


def test_status_update_appends_an_event(client, engine):
    client.post("/postings/1/apply", follow_redirects=True)
    client.post("/applications/1/status", data={"status": "interview"},
                follow_redirects=True)

    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        assert s.query(StatusEvent).count() == 2
        assert s.get(Application, 1).status == "interview"
    finally:
        s.close()


def test_duplicate_status_is_rejected(client, engine):
    """The guard: recording the same status twice must not log a second event."""
    client.post("/postings/1/apply", follow_redirects=True)
    client.post("/applications/1/status", data={"status": "applied"},
                follow_redirects=True)

    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        assert s.query(StatusEvent).count() == 1      # not 2
    finally:
        s.close()


def test_unknown_status_is_rejected(client):
    response = client.post("/postings/1/apply", follow_redirects=True)
    assert response.status_code == 200
    response = client.post("/applications/1/status", data={"status": "banana"})
    assert response.status_code == 400
