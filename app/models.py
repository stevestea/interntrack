"""SQLAlchemy models for InternTrack.

Read docs/SCHEMA.md before editing this file. The reasoning behind each
table lives there; this file is only the implementation.

STATUS: Company is written as a worked example. The other four models are
yours to write (see the TODOs at the bottom).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared base class for every model.

    SQLAlchemy collects table definitions from every class that inherits
    from this one. That collection (Base.metadata) is what lets us create
    the whole database with a single call later.
    """


# ---------------------------------------------------------------------------
# WORKED EXAMPLE - read every comment here, then write the rest yourself.
# ---------------------------------------------------------------------------


class Company(Base):
    __tablename__ = "companies"

    # Every table needs a primary key: the column that uniquely identifies
    # a row. An auto-incrementing integer is the boring, correct default.
    id: Mapped[int] = mapped_column(primary_key=True)

    # Mapped[str] means "this column can never be NULL".
    # Mapped[str | None] would mean it is nullable. The type annotation is
    # not decoration here - SQLAlchemy reads it to decide nullability.
    #
    # unique=True tells the DATABASE to reject a duplicate company name.
    # We enforce this in the database rather than in Python because Python
    # checks can be bypassed (a second process, a manual import, a bug),
    # while the database constraint cannot.
    name: Mapped[str] = mapped_column(String(200), unique=True)

    # Nullable: we often will not know the industry.
    industry: Mapped[str | None] = mapped_column(String(100))

    # server_default=func.now() lets the DATABASE fill the timestamp in.
    # Using the database clock instead of Python's keeps timestamps
    # consistent even if code runs on a machine with a wrong clock.
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # relationship() is the ORM convenience layer. It does NOT create a
    # column - the actual link is the company_id foreign key over on
    # Posting. This just lets you write `company.postings` in Python
    # instead of writing a JOIN by hand every time.
    #
    # back_populates wires the two sides together so that both stay in
    # sync in memory. The matching attribute on Posting must be `company`.
    postings: Mapped[list["Posting"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        # A readable repr saves real time when debugging in the shell.
        # Without it you get <Company object at 0x000001A2...>, which
        # tells you nothing.
        return f"<Company id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# YOUR TURN
# ---------------------------------------------------------------------------
#
# Write the four models below, following docs/SCHEMA.md for the columns and
# the Company example above for the style.
#
# TODO 1: class Posting(Base)  -> __tablename__ = "postings"
#   - id, title, location, remote, url, description, date_posted, source,
#     created_at
#   - company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
#   - company: the other half of Company.postings (back_populates="postings")
#   - url must be unique - it is the dedup key. Think about why the database
#     is the right place to enforce that.
#   - description should be Text, not String(n): job descriptions are long
#     and you do not want to pick an arbitrary length limit.
#
# TODO 2: class Application(Base)  -> __tablename__ = "applications"
#   - id, status, applied_at, notes
#   - posting_id: unique foreign key to postings.id
#     (unique because you apply to a given posting at most once - let the
#     database say so)
#
# TODO 3: class StatusEvent(Base)  -> __tablename__ = "status_events"
#   - id, status, occurred_at
#   - application_id: foreign key to applications.id (NOT unique - the whole
#     point is many events per application)
#
# TODO 4: class PostingSkill(Base)  -> __tablename__ = "posting_skills"
#   - posting_id: ForeignKey("postings.id"), primary_key=True
#   - skill: String(80), primary_key=True
#   - Two primary_key=True columns is a COMPOSITE primary key: the pair must
#     be unique, so the same skill cannot be recorded twice for one posting.
#     This is the shape that makes the skill-frequency GROUP BY work.
#
# When all four are written, tell me and I will review it line by line.


class Posting(Base):
    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(120))
    remote: Mapped[bool] = mapped_column(default=False)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    date_posted: Mapped[date | None] = mapped_column()
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    company: Mapped["Company"] = relationship(back_populates="postings")

    def __repr__(self) -> str:
        return f"<Posting id={self.id} title={self.title!r}>"