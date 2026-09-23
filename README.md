# InternTrack

A Flask web application that ingests internship and job postings, tracks
applications through a status pipeline, and analyzes required-skill frequency
across the collected postings.

Built to answer two questions at once: *where am I in my applications?* and
*what is the market actually asking for?*

**Status:** in development. The data model is complete; ingestion, web layer
and analytics are in progress. See [PLAN.md](PLAN.md) for the phase breakdown.

---

## Why it exists

Most application trackers only store jobs you applied to. That tells you about
your own behavior but nothing about the market.

InternTrack stores **every posting collected**, whether or not an application
follows. A posting with no linked application is simply one that was skipped.
That single decision is what makes the skill-frequency analysis possible — the
headline number ("Python appears in 78% of tracked postings") is computed over
the full corpus, not just the subset applied to.

## Design decisions

**Ingestion is decoupled from storage.** A CSV reader and a scraper both
produce the same normalized rows behind one `load_postings(rows)` interface.
Job boards block bots and change their markup; if scraping were the only path
in, a CSS class change would take the app down. This way a broken scraper
degrades to manual CSV import instead of an outage.

**Status history is an append-only event log, not a column.** `applications`
carries a cached current `status`, but the source of truth is `status_events` —
one row per transition with its own timestamp. A single overwritten column
cannot answer *"how many days between applying and hearing back?"*, which is
the most useful metric the app produces.

**Deduplication is enforced by the database.** `postings.url` carries a UNIQUE
constraint rather than a Python-side check. A Python check can be bypassed by a
concurrent import, a manual insert, or a bug; a database constraint cannot.
Re-importing the same CSV is a no-op instead of 200 duplicate rows.

**Skills live in a join table.** `posting_skills` uses a composite primary key
of `(posting_id, skill)`. Storing `"python, sql, aws"` in a column would mean
every analysis begins with string splitting and the field could never be
indexed. This shape reduces the headline query to a single `GROUP BY`.

## Schema

Five tables. Full reasoning in [docs/SCHEMA.md](docs/SCHEMA.md).

| Table | Holds | Notes |
|---|---|---|
| `companies` | one row per company | normalized so name variants don't split analytics |
| `postings` | every posting collected | `url` UNIQUE — the dedup key |
| `applications` | postings applied to | one-to-one with a posting |
| `status_events` | every status transition | append-only; timestamps enable elapsed-time analysis |
| `posting_skills` | skills extracted per posting | composite PK, many-to-many |

## Stack

Python 3.11 · Flask · SQLAlchemy 2.0 · SQLite (PostgreSQL in production) ·
pandas · pytest · GitHub Actions

## Running locally

```bash
git clone https://github.com/stevestea/interntrack.git
cd interntrack

py -m venv .venv                 # Windows
.\.venv\Scripts\Activate.ps1

# python3 -m venv .venv          # macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

Verify the models load:

```bash
python -c "from app.models import Base; print(sorted(Base.metadata.tables))"
```

Expected: `['applications', 'companies', 'posting_skills', 'postings', 'status_events']`

## Roadmap

- [x] Schema design and SQLAlchemy models
- [ ] CSV ingestion with validation and deduplication
- [ ] Flask routes: posting list, detail, status updates
- [ ] Analytics: skill frequency, funnel conversion, response-time distribution
- [ ] Test suite and CI
- [ ] Deployment

## Author

Luong Gia Bao Nguyen — [github.com/stevestea](https://github.com/stevestea)
