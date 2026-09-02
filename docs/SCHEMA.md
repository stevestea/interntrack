# Database schema

Five tables. Read the reasoning before you write the models — the "why" is what
you'll be asked about in an interview, not the syntax.

---

## companies

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL UNIQUE | |
| industry | TEXT | nullable |
| created_at | DATETIME | |

**Why a separate table:** if company name lived as a string on every posting,
"Datadog" and "DataDog " become two different companies and your analytics
silently split. Normalizing it means one row, one identity, and you can ask
"how many postings did each company put out" with a GROUP BY.

---

## postings

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| company_id | INTEGER FK -> companies.id | |
| title | TEXT NOT NULL | |
| location | TEXT | |
| remote | BOOLEAN | |
| url | TEXT UNIQUE | the dedup key |
| description | TEXT | raw text, used for skill extraction |
| date_posted | DATE | |
| source | TEXT | linkedin / handshake / careers page |
| created_at | DATETIME | when *you* ingested it |

**Why `url` is UNIQUE:** it's your natural dedup key. Re-import the same CSV
twice and you want the second import to be a no-op, not 200 duplicate rows.
Let the database enforce that rather than checking in Python — the DB is the
only place that can guarantee it.

**Why keep `description`:** the skill-frequency analysis reads it. Don't throw
away raw data you might want to re-analyze with better logic later.

**Note `date_posted` vs `created_at`:** these are different questions. One is
"when did the company post this," the other is "when did I find it." You will
want both.

---

## applications

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| posting_id | INTEGER FK -> postings.id UNIQUE | |
| status | TEXT | current status, denormalized for fast queries |
| applied_at | DATE | |
| notes | TEXT | |

**Why separate from postings:** you will track postings you never applied to.
That's a feature — it's what lets you analyze the whole market instead of only
your own applications. A posting with no application row is simply one you
skipped.

---

## status_events

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| application_id | INTEGER FK -> applications.id | |
| status | TEXT | applied / oa / interview / offer / rejected / ghosted |
| occurred_at | DATETIME | |

**Why an event table instead of just overwriting `status`:** if you only store
the current status, you can never answer "how long between applying and hearing
back." That question is your best analytics bullet. Events give you the
timeline; the `status` column on `applications` is a cached copy of the latest
event so the list page doesn't need a subquery per row.

This is called an event-sourced or append-only pattern. Worth knowing the name.

---

## posting_skills

| column | type | notes |
|---|---|---|
| posting_id | INTEGER FK | composite PK with skill |
| skill | TEXT | normalized lowercase |

**Why a join table:** a posting has many skills and a skill appears in many
postings — many-to-many. Storing `"python, sql, aws"` in one column means every
analysis starts with string splitting, and you can never index it. This shape
lets you write:

    SELECT skill, COUNT(*) FROM posting_skills GROUP BY skill ORDER BY 2 DESC;

That one query is the headline number on your dashboard.

---

## Your task (Phase 1)

Write these as SQLAlchemy models in `app/models.py`. Use the declarative style.
Get the foreign keys and the relationships right; don't worry about migrations
yet.

When you're stuck or done, show me the file and I'll review it.
