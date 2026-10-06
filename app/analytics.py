"""Analytics over the posting corpus and the application pipeline.

Division of labour between SQL and pandas, which is the real engineering
decision in this file:

  SQL does the filtering, joining and counting - work the database is built
  for and can do over millions of rows without loading them into memory.

  pandas does the shaping afterwards - percentages, pivots, date bucketing,
  descriptive statistics. Work that is awkward in SQL and natural in a
  DataFrame.

The wrong version of this file would `SELECT *` everything and do the
counting in Python. That works at 5 rows and falls over at 500,000.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, Company, Posting, PostingSkill, StatusEvent

# The pipeline in order. Used to order the funnel, which is not alphabetical
# and not frequency-ordered - it is sequential, and that ordering carries
# meaning.
FUNNEL_ORDER = ["applied", "oa", "interview", "offer"]
TERMINAL = ["rejected", "ghosted"]


def skill_frequency(session: Session, top_n: int = 15) -> pd.DataFrame:
    """How often each skill appears across all collected postings.

    The headline number of the whole project. Counting happens in SQL via
    GROUP BY; pandas only adds the percentage column.

    Returns columns: skill, count, pct
    """
    total_postings = session.scalar(select(func.count()).select_from(Posting)) or 0

    rows = session.execute(
        select(PostingSkill.skill, func.count().label("count"))
        .group_by(PostingSkill.skill)
        .order_by(func.count().desc(), PostingSkill.skill)
        .limit(top_n)
    ).all()

    df = pd.DataFrame(rows, columns=["skill", "count"])
    if df.empty:
        return pd.DataFrame(columns=["skill", "count", "pct"])

    # pandas doing what pandas is for: a derived column across the frame.
    df["pct"] = (df["count"] / total_postings * 100).round(1) if total_postings else 0.0
    return df


def funnel(session: Session) -> pd.DataFrame:
    """How many applications reached each stage.

    Counted from status_events, not from applications.status. That matters:
    an application now marked 'rejected' still passed THROUGH 'interview',
    and the funnel should credit that. Reading the cached current status
    would undercount every stage except the last one.

    This is the clearest payoff of the append-only event log.

    Returns columns: stage, count, pct_of_applied
    """
    rows = session.execute(
        select(StatusEvent.status, func.count(func.distinct(StatusEvent.application_id)))
        .group_by(StatusEvent.status)
    ).all()

    reached = dict(rows)
    applied = reached.get("applied", 0)

    df = pd.DataFrame(
        [{"stage": s, "count": reached.get(s, 0)} for s in FUNNEL_ORDER]
    )
    df["pct_of_applied"] = (
        (df["count"] / applied * 100).round(1) if applied else 0.0
    )
    return df


def response_times(session: Session) -> dict[str, float | int | None]:
    """Days between applying and the first response, per application.

    "Response" means any status event after the opening 'applied' one.
    Applications still waiting contribute nothing - they have no response
    yet, and counting them as zero would drag the median down and lie.

    This function exists only because status is an event log. With a single
    overwritten column the 'applied' timestamp would be gone.

    Returns: median_days, mean_days, fastest, slowest, n (how many responded)
    """
    rows = session.execute(
        select(StatusEvent.application_id, StatusEvent.status, StatusEvent.occurred_at)
        .order_by(StatusEvent.application_id, StatusEvent.occurred_at)
    ).all()

    if not rows:
        return {"median_days": None, "mean_days": None, "fastest": None,
                "slowest": None, "n": 0}

    df = pd.DataFrame(rows, columns=["application_id", "status", "occurred_at"])
    df["occurred_at"] = pd.to_datetime(df["occurred_at"])

    gaps = []
    # groupby: split the frame into one group per application, then work on
    # each group independently. The pandas idiom for "per X, compute Y".
    for _, group in df.groupby("application_id"):
        group = group.sort_values("occurred_at")
        first_applied = group[group["status"] == "applied"]
        if first_applied.empty:
            continue
        t0 = first_applied.iloc[0]["occurred_at"]
        after = group[group["occurred_at"] > t0]
        after = after[after["status"] != "applied"]
        if after.empty:
            continue  # still waiting - excluded on purpose
        gaps.append((after.iloc[0]["occurred_at"] - t0).total_seconds() / 86400)

    if not gaps:
        return {"median_days": None, "mean_days": None, "fastest": None,
                "slowest": None, "n": 0}

    s = pd.Series(gaps)
    return {
        "median_days": round(float(s.median()), 1),
        "mean_days": round(float(s.mean()), 1),
        "fastest": round(float(s.min()), 1),
        "slowest": round(float(s.max()), 1),
        "n": len(gaps),
    }


def postings_over_time(session: Session) -> pd.DataFrame:
    """Posting volume per week, by date_posted.

    Date bucketing is where pandas clearly beats SQL - resample() handles
    week boundaries, and reindexing fills weeks that had zero postings.
    Without that fill, a gap in hiring would render as a straight line
    between two points instead of a visible dip.

    Returns columns: week, count
    """
    rows = session.execute(
        select(Posting.date_posted).where(Posting.date_posted.is_not(None))
    ).all()

    if not rows:
        return pd.DataFrame(columns=["week", "count"])

    df = pd.DataFrame(rows, columns=["date_posted"])
    df["date_posted"] = pd.to_datetime(df["date_posted"])

    weekly = (
        df.set_index("date_posted")
        .resample("W")           # bucket into calendar weeks
        .size()                  # count rows per bucket
        .reset_index(name="count")
        .rename(columns={"date_posted": "week"})
    )
    weekly["week"] = weekly["week"].dt.strftime("%b %d")
    return weekly


def top_companies(session: Session, top_n: int = 8) -> pd.DataFrame:
    """Which companies posted the most roles.

    A plain JOIN + GROUP BY. Here SQL does everything and pandas is only a
    container - which is the right call when no reshaping is needed.

    Returns columns: company, count
    """
    rows = session.execute(
        select(Company.name, func.count(Posting.id).label("count"))
        .join(Posting, Posting.company_id == Company.id)
        .group_by(Company.name)
        .order_by(func.count(Posting.id).desc(), Company.name)
        .limit(top_n)
    ).all()
    return pd.DataFrame(rows, columns=["company", "count"])


def headline_stats(session: Session) -> dict[str, int]:
    """The numbers for the stat tiles at the top of the dashboard."""
    return {
        "postings": session.scalar(select(func.count()).select_from(Posting)) or 0,
        "companies": session.scalar(select(func.count()).select_from(Company)) or 0,
        "applications": session.scalar(select(func.count()).select_from(Application)) or 0,
        "remote": session.scalar(
            select(func.count()).select_from(Posting).where(Posting.remote.is_(True))
        ) or 0,
    }
