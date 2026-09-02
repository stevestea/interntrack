# InternTrack — Project Plan

**Owner:** Luong Gia Bao (Bao) Nguyen
**Started:** 2026-09-02
**Target v1 (deployed, tested):** 2026-09-23 — before the October application push

---

## What this is

A Flask web app that ingests internship/job postings from CSV (with optional
URL scraping), tracks each application through a pipeline, and runs analytics
over the whole corpus of postings.

Two halves, deliberately:

1. **Software engineering half** — schema design, SQL, web routes, tests, CI, deploy.
2. **Data/analytics half** — skill frequency extraction, funnel conversion,
   posting volume over time, response-time distributions.

The analytics half is the point, not a bolt-on. It is what makes this a data
project instead of a CRUD app, and it is where the BAT coursework shows up.

## Why this project (the resume argument)

Current resume gaps this is built to close:

| Gap | How this closes it |
|---|---|
| Nothing has shipped — every bullet is "analyzed" / "in progress" | A deployed URL and a finished repo |
| No SQL, web framework, DB, testing, or CI on the skills line | All five are load-bearing here |
| Only quantified bullet is in the food-service job | The app generates its own numbers |
| PROJECTS has one entry, in progress | This becomes the second, completed |

## Non-goals

- Not a job board. It does not search for jobs.
- Not multi-user. Single user, no auth in v1.
- Not a scraper-first tool. CSV is the primary path; scraping is a bonus that
  is allowed to break.

## Architecture decision: decoupled ingestion

Ingestion is separated from storage behind a single `load_postings(rows)`
interface. A CSV reader and a scraper both produce the same normalized rows.

**Why:** job boards block bots and change their markup. If the scraper is the
only way in, a CSS class change takes down the whole app. This way a broken
scraper degrades to manual CSV import instead of an outage.

## Stack

- Python 3.11.9 (python.org build, invoked via the `py` launcher — MSYS2
  Python is first on PATH on this machine and must be avoided; it has no
  matching PyPI wheels, so pandas would build from source)
- Flask, SQLAlchemy, SQLite (Postgres for deploy)
- pandas for analytics, Chart.js for the frontend charts
- pytest, GitHub Actions
- Deploy target: TBD (Render or Fly.io free tier)

## Phases

| # | Phase | Bao writes | Claude does |
|---|---|---|---|
| 0 | Setup | venv, git init, first commit | structure, explains each piece |
| 1 | Schema | SQLAlchemy models | schema design + review |
| 2 | Ingestion | the CSV parser | spec + test fixtures |
| 3 | Web app | routes and templates | one worked route as reference |
| 4 | Analytics | the pandas aggregations | query design + chart review |
| 5 | Tests/CI | tests alongside Claude | pytest patterns, workflow file |
| 6 | Deploy/README | the writeup | deploy walkthrough, resume bullets |

## Status log

- 2026-09-02 — Plan locked. Repo scaffolded. Phase 0 in progress.
- 2026-09-02 — Toolchain gotcha: `python` on this machine resolves to MSYS2
  (Unix layout, `bin/` not `Scripts/`, no compatible wheels). Always use `py`
  to create the venv.
