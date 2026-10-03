"""Flask application: routes, request handling, template rendering.

Structure note: this uses the "application factory" pattern - create_app()
builds and returns the app rather than creating one at import time. That
makes it possible to build a second app with different settings in tests,
which matters in Phase 5.
"""

from __future__ import annotations

from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db import DB_PATH, get_session, init_db
from app.models import Application, Company, Posting, PostingSkill, StatusEvent

# The pipeline stages an application moves through, in order.
STATUSES = ["applied", "oa", "interview", "offer", "rejected", "ghosted"]


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-only-not-a-real-secret"  # flash() needs one
    init_db()

    @app.route("/")
    def index():
        """List postings, with optional filtering.

        selectinload(Posting.company) is doing real work here. Without it,
        rendering 100 postings issues 1 query for the postings plus 100 more
        - one per posting - to fetch each company name. That is the N+1 query
        problem. selectinload fetches all the companies in one extra query
        instead, so the page costs 2 queries regardless of row count.
        """
        q = (request.args.get("q") or "").strip()
        remote_only = request.args.get("remote") == "1"
        status = (request.args.get("status") or "").strip()

        stmt = (
            select(Posting)
            .options(
                selectinload(Posting.company),
            )
            .order_by(Posting.date_posted.desc().nullslast(), Posting.id.desc())
        )

        if q:
            like = f"%{q}%"
            stmt = stmt.join(Company).where(
                Posting.title.ilike(like) | Company.name.ilike(like)
            )
        if remote_only:
            stmt = stmt.where(Posting.remote.is_(True))

        session = get_session()
        try:
            postings = list(session.scalars(stmt))

            # Which postings have applications, and at what status.
            apps = {
                a.posting_id: a
                for a in session.scalars(select(Application))
            }

            if status:
                postings = [
                    p for p in postings
                    if apps.get(p.id) and apps[p.id].status == status
                ]

            total = session.scalar(select(func.count()).select_from(Posting))
            applied_count = session.scalar(select(func.count()).select_from(Application))

            return render_template(
                "index.html",
                postings=postings,
                apps=apps,
                q=q,
                remote_only=remote_only,
                status=status,
                statuses=STATUSES,
                total=total,
                applied_count=applied_count,
            )
        finally:
            session.close()

    @app.route("/postings/<int:posting_id>")
    def posting_detail(posting_id: int):
        session = get_session()
        try:
            posting = session.scalar(
                select(Posting)
                .options(selectinload(Posting.company))
                .where(Posting.id == posting_id)
            )
            if posting is None:
                abort(404)

            skills = list(
                session.scalars(
                    select(PostingSkill.skill)
                    .where(PostingSkill.posting_id == posting_id)
                    .order_by(PostingSkill.skill)
                )
            )
            application = session.scalar(
                select(Application).where(Application.posting_id == posting_id)
            )
            events = []
            if application:
                events = list(
                    session.scalars(
                        select(StatusEvent)
                        .where(StatusEvent.application_id == application.id)
                        .order_by(StatusEvent.occurred_at.desc())
                    )
                )

            return render_template(
                "detail.html",
                posting=posting,
                skills=skills,
                application=application,
                events=events,
                statuses=STATUSES,
            )
        finally:
            session.close()

    @app.route("/postings/<int:posting_id>/apply", methods=["POST"])
    def apply(posting_id: int):
        """Record an application, and its first status event.

        Note both writes happen together: the Application row AND the opening
        StatusEvent. The event log has to start the moment the application
        does, or the timeline has a hole in it.
        """
        session = get_session()
        try:
            posting = session.get(Posting, posting_id)
            if posting is None:
                abort(404)

            existing = session.scalar(
                select(Application).where(Application.posting_id == posting_id)
            )
            if existing is None:
                application = Application(
                    posting_id=posting_id,
                    status="applied",
                    applied_at=date.today(),
                )
                session.add(application)
                session.flush()
                session.add(
                    StatusEvent(application_id=application.id, status="applied")
                )
                session.commit()
                flash("Marked as applied.", "ok")
            else:
                flash("Already applied to this posting.", "warn")

            return redirect(url_for("posting_detail", posting_id=posting_id))
        finally:
            session.close()

    @app.route("/applications/<int:application_id>/status", methods=["POST"])
    def update_status(application_id: int):
        """Append a status event and update the cached current status.

        Two writes on purpose. `status_events` is the source of truth - an
        append-only log that preserves the full timeline. `applications.status`
        is a denormalized cache of the latest one, so the list page can show
        current status without a subquery per row.

        The cache is allowed to exist because it can always be rebuilt from
        the log. The reverse would not be true.
        """
        new_status = (request.form.get("status") or "").strip()
        if new_status not in STATUSES:
            abort(400)

        session = get_session()
        try:
            application = session.get(Application, application_id)
            if application is None:
                abort(404)

            session.add(StatusEvent(application_id=application.id, status=new_status))
            application.status = new_status
            session.commit()
            flash(f"Status updated to {new_status}.", "ok")

            return redirect(
                url_for("posting_detail", posting_id=application.posting_id)
            )
        finally:
            session.close()

    @app.template_filter("fmtdate")
    def fmtdate(value) -> str:
        """Jinja filter: render a date, or an em dash when it is missing."""
        return value.strftime("%b %d, %Y") if value else "—"

    return app


app = create_app()


if __name__ == "__main__":
    print(f"Using database: {DB_PATH}")
    app.run(debug=True, port=5000)
