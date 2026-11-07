"""Group B medium GET smoke test for PG-only runtime (no research.db)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

from services.db.pg_pool import pg_connection


def _one(sql: str, key: str) -> str:
    try:
        pg = pg_connection()
        try:
            row = pg.execute(sql).fetchone()
            return str(row[key]) if row and row.get(key) else ""
        finally:
            pg.close()
    except Exception:
        return ""


def main() -> int:
    app = Flask(__name__)
    app.secret_key = os.environ["SCIPAL_SECRET_KEY"]
    user = _one("SELECT user_id FROM memberships LIMIT 1", "user_id")
    workspace = _one("SELECT workspace_id FROM memberships LIMIT 1", "workspace_id")
    cookie = SecureCookieSessionInterface().get_signing_serializer(app).dumps(
        {"user_id": user, "workspace_id": workspace}
    )

    review_project = _one("SELECT project_id FROM review_projects LIMIT 1", "project_id")
    experiment = _one("SELECT experiment_id FROM experiments LIMIT 1", "experiment_id")
    review = _one("SELECT review_id FROM reviews LIMIT 1", "review_id")
    protocol = _one("SELECT protocol_id FROM protocol_imports LIMIT 1", "protocol_id")
    paper = _one("SELECT paper_id FROM papers LIMIT 1", "paper_id")
    base = os.environ.get("SCIPAL_SMOKE_BASE", "http://127.0.0.1")

    urls = []
    if review_project:
        urls += [
            f"/api/review-projects/{review_project}/brief",
            f"/api/review-projects/{review_project}/conflicts",
            f"/api/review-projects/{review_project}/events",
            f"/api/review-projects/{review_project}/evidence",
            f"/api/review-projects/{review_project}/evidence.csv",
            f"/api/review-projects/{review_project}/export.json",
            f"/api/review-projects/{review_project}/kappa",
            f"/api/review-projects/{review_project}/members",
            f"/api/review-projects/{review_project}/prisma",
            f"/api/review-projects/{review_project}/risk-of-bias",
            f"/api/review-projects/{review_project}/webhooks",
        ]
    if experiment:
        urls += [
            f"/api/experiments/{experiment}/revisions",
            f"/api/experiments/{experiment}/audit",
            f"/api/experiments/{experiment}/signatures",
            f"/api/experiments/{experiment}/access-requests",
        ]
    if review:
        urls += [f"/api/reviews/{review}"]
    if protocol:
        urls += [f"/api/protocols/{protocol}/runs"]
    if paper:
        urls += [f"/api/papers/{paper}/supplementary"]

    session = requests.Session()
    session.cookies.set("session", cookie, domain="127.0.0.1")
    statuses = {}
    failures = []
    for url in urls:
        try:
            response = session.get(base + url, timeout=60)
            statuses[url] = response.status_code
            if response.status_code >= 500:
                failures.append({"url": url, "status": response.status_code})
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": url, "error": str(exc)[:200]})
    print(json.dumps({"tested": len(urls), "statuses": statuses, "failures": failures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
