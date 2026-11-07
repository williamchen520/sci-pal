"""GET-route smoke test for the PG-only runtime (no research.db)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from api_server import app
from services.db.pg_pool import pg_connection

TOKENS = {
    "filename": "index.html",
    "path": "index.html",
    "paper_id": "",
    "sentence_id": "",
    "project_id": "",
    "experiment_id": "",
    "run_id": "",
    "review_id": "",
    "claim_id": "",
    "profile_id": "1",
    "task_id": "",
    "workspace_id": "",
    "user_id": "",
    "pack_id": "",
    "protocol_id": "",
    "artifact_id": "",
    "file_id": "",
    "supp_id": "",
    "term": "hepatocellular",
    "name": "",
}


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
    TOKENS["paper_id"] = _one("SELECT paper_id FROM papers LIMIT 1", "paper_id")
    TOKENS["sentence_id"] = _one("SELECT sentence_id FROM sentences LIMIT 1", "sentence_id")
    TOKENS["workspace_id"] = _one("SELECT workspace_id FROM memberships LIMIT 1", "workspace_id")
    TOKENS["user_id"] = _one("SELECT user_id FROM memberships LIMIT 1", "user_id")
    TOKENS["project_id"] = _one("SELECT project_id FROM projects LIMIT 1", "project_id")
    TOKENS["experiment_id"] = _one("SELECT experiment_id FROM experiments LIMIT 1", "experiment_id")
    TOKENS["run_id"] = _one("SELECT run_id FROM experiment_runs LIMIT 1", "run_id")
    TOKENS["review_id"] = _one("SELECT review_id FROM reviews LIMIT 1", "review_id")
    TOKENS["claim_id"] = _one("SELECT claim_id FROM claim_cards LIMIT 1", "claim_id")
    TOKENS["protocol_id"] = _one("SELECT protocol_id FROM protocol_imports LIMIT 1", "protocol_id")

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = TOKENS["user_id"]
        session["workspace_id"] = TOKENS["workspace_id"]

    failures = []
    skipped = []
    tested = 0
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if "GET" not in rule.methods or rule.rule.startswith("/static"):
            continue
        url = rule.rule
        missing = False
        for token, value in TOKENS.items():
            for form in (f"<{token}>", f"<int:{token}>", f"<path:{token}>"):
                if form in url:
                    if not value:
                        missing = True
                    url = url.replace(form, value)
        if missing or "<" in url:
            skipped.append(rule.rule)
            continue
        if rule.rule.endswith("/trace") and TOKENS["sentence_id"]:
            url += f"?sentence_id={TOKENS['sentence_id']}"
        try:
            response = client.get(url, timeout=120)
            tested += 1
            if response.status_code >= 500:
                failures.append({"route": rule.rule, "url": url, "status": response.status_code})
        except Exception as exc:  # noqa: BLE001
            tested += 1
            failures.append({"route": rule.rule, "url": url, "error": str(exc)[:200]})

    print(json.dumps({"tested": tested, "skipped": skipped, "failures": failures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
