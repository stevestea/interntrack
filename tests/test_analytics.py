"""Tests for the analytics layer.

These are the highest-value tests in the project: a wrong number here looks
plausible on a dashboard, so nothing catches it except a test that knows the
right answer in advance.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.analytics import (
    funnel,
    headline_stats,
    postings_over_time,
    response_times,
    skill_frequency,
    top_companies,
)
from app.ingest import load_postings
from app.models import Application, Company, Posting, StatusEvent


# --- skill_frequency -----------------------------------------------------

def test_skill_frequency_counts_and_percentages(session, sample_rows):
    load_postings(sample_rows, session)        # 2 postings, both mention Python
    df = skill_frequency(session)

    python = df[df["skill"] == "python"].iloc[0]
    assert python["count"] == 2
    assert python["pct"] == 100.0


def test_skill_frequency_is_ordered_by_count_descending(session, sample_rows):
    load_postings(sample_rows, session)
    df = skill_frequency(session)
    counts = df["count"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_skill_frequency_is_empty_when_there_is_no_data(session):
    df = skill_frequency(session)
    assert df.empty
    assert list(df.columns) == ["skill", "count", "pct"]


def test_skill_frequency_respects_top_n(session, sample_rows):
    load_postings(sample_rows, session)
    assert len(skill_frequency(session, top_n=2)) == 2


# --- funnel --------------------------------------------------------------

def test_funnel_credits_stages_an_application_passed_through(session, rejected_application):
    """The whole point of the event log.

    This application's current status is 'rejected', but it reached
    'interview'. Reading applications.status would report 0 interviews.
    """
    df = funnel(session)
    by_stage = dict(zip(df["stage"], df["count"]))

    assert by_stage["applied"] == 1
    assert by_stage["interview"] == 1      # would be 0 if read from the cache
    assert by_stage["offer"] == 0


def test_funnel_percentages_are_relative_to_applied(session, rejected_application):
    df = funnel(session)
    interview = df[df["stage"] == "interview"].iloc[0]
    assert interview["pct_of_applied"] == 100.0


def test_funnel_counts_distinct_applications_not_events(session, rejected_application):
    """Two 'applied' events for one application is still one application."""
    session.add(StatusEvent(
        application_id=rejected_application.id,
        status="applied",
        occurred_at=datetime(2026, 9, 2, 9, 0),
    ))
    session.commit()

    df = funnel(session)
    assert df[df["stage"] == "applied"].iloc[0]["count"] == 1


def test_funnel_is_all_zeros_with_no_applications(session):
    df = funnel(session)
    assert df["count"].sum() == 0


# --- response_times ------------------------------------------------------

def test_response_time_measures_applied_to_first_response(session, rejected_application):
    """applied -> interview is 10 days; the later rejection must not count."""
    stats = response_times(session)
    assert stats["n"] == 1
    assert stats["median_days"] == 10.0


def test_response_time_excludes_applications_still_waiting(session, rejected_application):
    """A pending application contributes nothing - not a zero.

    Counting it as zero days would drag the median down and misrepresent it.
    """
    company = session.query(Company).first()
    posting = Posting(company_id=company.id, title="Pending",
                      url="https://example.com/pending")
    session.add(posting)
    session.flush()
    pending = Application(posting_id=posting.id, status="applied")
    session.add(pending)
    session.flush()
    session.add(StatusEvent(application_id=pending.id, status="applied",
                            occurred_at=datetime(2026, 9, 5, 9, 0)))
    session.commit()

    stats = response_times(session)
    assert stats["n"] == 1             # still 1, not 2
    assert stats["median_days"] == 10.0


def test_response_time_is_none_when_nothing_has_responded(session):
    stats = response_times(session)
    assert stats["n"] == 0
    assert stats["median_days"] is None


def test_response_time_median_across_several_applications(session):
    """Median of 2, 10, 30 is 10 - not the mean of 14."""
    company = Company(name="Acme")
    session.add(company)
    session.flush()

    t0 = datetime(2026, 9, 1, 9, 0)
    for i, gap in enumerate([2, 10, 30]):
        posting = Posting(company_id=company.id, title=f"Role {i}",
                          url=f"https://example.com/{i}")
        session.add(posting)
        session.flush()
        app_row = Application(posting_id=posting.id, status="interview")
        session.add(app_row)
        session.flush()
        session.add_all([
            StatusEvent(application_id=app_row.id, status="applied", occurred_at=t0),
            StatusEvent(application_id=app_row.id, status="interview",
                        occurred_at=t0 + timedelta(days=gap)),
        ])
    session.commit()

    stats = response_times(session)
    assert stats["n"] == 3
    assert stats["median_days"] == 10.0
    assert stats["fastest"] == 2.0
    assert stats["slowest"] == 30.0


# --- postings_over_time --------------------------------------------------

def test_postings_over_time_buckets_into_weeks(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    # Two postings in one week, one three weeks later.
    for i, d in enumerate([date(2026, 8, 3), date(2026, 8, 5), date(2026, 8, 24)]):
        session.add(Posting(company_id=company.id, title=f"R{i}",
                            url=f"https://example.com/w{i}", date_posted=d))
    session.commit()

    df = postings_over_time(session)
    assert df["count"].sum() == 3
    assert df["count"].max() == 2          # the two same-week postings


def test_postings_over_time_ignores_rows_without_a_date(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    session.add(Posting(company_id=company.id, title="No date",
                        url="https://example.com/nd", date_posted=None))
    session.commit()
    assert postings_over_time(session).empty


# --- top_companies and headline_stats ------------------------------------

def test_top_companies_counts_postings_per_company(session, sample_rows):
    load_postings(sample_rows, session)
    df = top_companies(session)
    assert set(df["company"]) == {"Datadog", "Rackspace"}
    assert df["count"].tolist() == [1, 1]


def test_headline_stats_reports_totals(session, sample_rows):
    load_postings(sample_rows, session)
    stats = headline_stats(session)
    assert stats["postings"] == 2
    assert stats["companies"] == 2
    assert stats["applications"] == 0
    assert stats["remote"] == 1
