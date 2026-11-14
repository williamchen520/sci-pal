#!/usr/bin/env python3
"""End-to-end smoke test for the scipal-paper plugin HTTP surface."""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", default="")
    parser.add_argument("--base", default=os.environ.get("SCIPAL_SMOKE_BASE", "http://127.0.0.1:5001"))
    args = parser.parse_args()

    paper_id = args.paper_id or _one("SELECT paper_id FROM papers ORDER BY created_at DESC LIMIT 1", "paper_id")
    if not paper_id:
        raise SystemExit("no paper_id")

    app = Flask(__name__)
    app.secret_key = os.environ["SCIPAL_SECRET_KEY"]
    cookie = SecureCookieSessionInterface().get_signing_serializer(app).dumps(
        {
            "user_id": _one("SELECT user_id FROM memberships LIMIT 1", "user_id"),
            "workspace_id": _one("SELECT workspace_id FROM memberships LIMIT 1", "workspace_id"),
        }
    )
    session = requests.Session()
    session.cookies.set("session", cookie, domain="127.0.0.1")
    base = args.base.rstrip("/")
    failures: list[str] = []
    results: dict[str, object] = {}

    def check(name: str, method: str, path: str, payload=None) -> requests.Response | None:
        try:
            response = session.request(method, base + path, json=payload, timeout=90)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {exc}")
            return None
        results[name] = response.status_code
        if response.status_code >= 400:
            failures.append(f"{name}: {response.status_code}")
        return response

    health = check("health", "GET", "/api/health")
    outline = check("outline", "GET", f"/api/papers/{paper_id}/outline")
    check("first", "GET", f"/api/papers/{paper_id}/paragraphs/first")
    analysis = check(
        "analysis",
        "GET",
        f"/api/papers/{paper_id}/analysis?compact=1&include_sections=0",
    )
    check(
        "evidence",
        "POST",
        f"/api/papers/{paper_id}/evidence",
        {"query": "molecular subtype", "top_k": 1},
    )
    check("code_links", "GET", f"/api/papers/{paper_id}/code-links")
    check("code_libraries", "GET", f"/api/papers/{paper_id}/code-libraries")
    modules = check("modules", "GET", f"/api/papers/{paper_id}/modules")
    check("data_flow", "GET", f"/api/papers/{paper_id}/data-flow")

    if outline is not None and outline.ok:
        types = {row.get("section_type") for row in outline.json().get("sections", [])}
        for section_type in ("results", "methods"):
            if section_type in types:
                check(
                    f"section_{section_type}",
                    "GET",
                    f"/api/papers/{paper_id}/sections/{section_type}",
                )
    if analysis is not None and analysis.ok:
        data = analysis.json()
        if data.get("outline") != []:
            failures.append("analysis: compact outline not empty")
        if not data.get("outline_summary", {}).get("section_count"):
            failures.append("analysis: no section_count")

    if modules is not None and modules.ok:
        module_rows = modules.json().get("modules", [])
        if module_rows:
            target = module_rows[0].get("path") or ""
            check(
                "replication_plan",
                "POST",
                f"/api/papers/{paper_id}/replication-plan",
                {"target": target},
            )

    print(json.dumps({"paper_id": paper_id, "status": results, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
