"""HTTP smoke test with a signed Flask session; one timeout per route."""

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
    cookie = SecureCookieSessionInterface().get_signing_serializer(app).dumps(
        {
            "user_id": _one("SELECT user_id FROM memberships LIMIT 1", "user_id"),
            "workspace_id": _one("SELECT workspace_id FROM memberships LIMIT 1", "workspace_id"),
        }
    )
    paper = _one("SELECT paper_id FROM papers LIMIT 1", "paper_id")
    sentence = _one("SELECT sentence_id FROM sentences LIMIT 1", "sentence_id")
    project = _one("SELECT project_id FROM projects LIMIT 1", "project_id")
    experiment = _one("SELECT experiment_id FROM experiments LIMIT 1", "experiment_id")
    claim = _one("SELECT claim_id FROM claim_cards LIMIT 1", "claim_id")
    review_project = _one("SELECT project_id FROM review_projects LIMIT 1", "project_id")
    review = _one("SELECT review_id FROM reviews LIMIT 1", "review_id")
    protocol = _one("SELECT protocol_id FROM protocol_imports LIMIT 1", "protocol_id")
    workspace = _one("SELECT workspace_id FROM memberships LIMIT 1", "workspace_id")
    base = os.environ.get("SCIPAL_SMOKE_BASE", "http://127.0.0.1")

    urls = [
        "/api/health",
        "/api/abstracts/list?page_size=1",
        "/api/papers",
        "/api/papers/local",
        "/api/projects",
        "/api/experiments",
        "/api/claims",
        "/api/notes",
        "/api/watch/profiles",
        "/api/tasks",
        "/api/workspaces",
        "/api/domain-packs",
        "/api/guard/stats",
        "/api/references",
        "/api/protocols",
        "/api/reviews",
        "/api/review-projects",
        "/api/qa/status",
        "/api/review/llm_status",
    ]
    if paper:
        urls += [f"/api/papers/{paper}", f"/api/papers/{paper}/graph", f"/api/abstracts/{paper}"]
    if sentence:
        urls += [f"/api/papers/{paper}/trace?sentence_id={sentence}"]
    if project:
        urls += [f"/api/projects/{project}", f"/api/projects/{project}/experiments"]
    if experiment:
        urls += [f"/api/experiments/{experiment}", f"/api/experiments/{experiment}/runs"]
    if claim:
        urls += [f"/api/claims/{claim}", f"/api/claims/{claim}/events"]
    if review_project:
        urls += [f"/api/review-projects/{review_project}"]
    if review:
        urls += [f"/api/reviews/{review}"]
    if protocol:
        urls += [f"/api/protocols/{protocol}"]
    if workspace:
        urls += [f"/api/workspaces/{workspace}/members"]

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
