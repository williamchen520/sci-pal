"""Group C heavy GET smoke test for PG-only runtime."""

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
    pg = pg_connection()
    try:
        row = pg.execute(sql).fetchone()
        return str(row[key]) if row and row.get(key) else ""
    finally:
        pg.close()


def main() -> int:
    app = Flask(__name__)
    app.secret_key = os.environ["SCIPAL_SECRET_KEY"]
    user = _one("SELECT user_id FROM memberships LIMIT 1", "user_id")
    workspace = _one("SELECT workspace_id FROM memberships LIMIT 1", "workspace_id")
    cookie = SecureCookieSessionInterface().get_signing_serializer(app).dumps(
        {"user_id": user, "workspace_id": workspace}
    )
    project = _one("SELECT project_id FROM review_projects LIMIT 1", "project_id")
    paper = _one("SELECT paper_id FROM papers LIMIT 1", "paper_id")
    sentence = _one("SELECT sentence_id FROM sentences WHERE paper_id = %s LIMIT 1" % ("'" + paper.replace("'", "''") + "'"), "sentence_id") if paper else ""
    base = os.environ.get("SCIPAL_SMOKE_BASE", "http://127.0.0.1")

    urls = []
    if project:
        urls += [
            f"/api/review-projects/{project}/prisma.svg",
            f"/api/review-projects/{project}/report.html",
            f"/api/review-projects/{project}/report.docx",
            f"/api/review-projects/{project}/report.pdf",
        ]
    if paper and sentence:
        urls += [f"/api/papers/{paper}/trace.png?sentence_id={sentence}"]

    session = requests.Session()
    session.cookies.set("session", cookie, domain="127.0.0.1")
    statuses = {}
    failures = []
    for url in urls:
        try:
            response = session.get(base + url, timeout=180)
            statuses[url] = response.status_code
            if response.status_code >= 500:
                failures.append({"url": url, "status": response.status_code})
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": url, "error": str(exc)[:200]})
    print(json.dumps({"tested": len(urls), "statuses": statuses, "failures": failures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
