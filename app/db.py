"""Database connection and session setup.

This file is plumbing: it decides WHERE the database lives and hands out
sessions to talk to it. No business logic belongs here.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

# Resolve paths relative to this file, never the current working directory.
# Otherwise the app finds its database only when launched from the project
# root - a classic source of "works on my machine".
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "interntrack.db"

# SQLite's URL format. Three slashes = a relative/absolute file path follows.
DATABASE_URL = f"sqlite:///{DB_PATH}"

# The engine owns the connection pool. One per application, created once.
# echo=True would print every SQL statement - useful when debugging, noisy
# otherwise.
engine = create_engine(DATABASE_URL, echo=False)

# A session is a single unit of work: you add objects, then commit or roll
# back. SessionLocal is a factory - call it to get a fresh session.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create the data directory and every table defined in models.py.

    create_all() is idempotent: existing tables are left alone, so running
    this twice is harmless. It does NOT alter tables whose definition has
    changed - that needs a migration tool, which this project doesn't use yet.
    """
    DATA_DIR.mkdir(exist_ok=True)
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Open a new session. Caller is responsible for closing it."""
    return SessionLocal()


if __name__ == "__main__":
    init_db()
    print(f"Database ready at {DB_PATH}")
    print("Tables:", ", ".join(sorted(Base.metadata.tables)))
