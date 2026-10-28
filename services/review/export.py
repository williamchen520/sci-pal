"""JSON export / import for systematic review projects."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict

from services.review import systematic


def export_project(conn: sqlite3.Connection, project_id: str) -> Dict:
    project = systematic.get_project(conn, project_id)
    if not project:
        raise KeyError("project not found")
    papers = [
        row[0]
        for row in conn.execute(
            "SELECT paper_id FROM review_project_papers WHERE project_id = ?", (project_id,)
        )
    ]
    screening = [
        {
            "paper_id": row[0],
            "stage": row[1],
            "decision": row[2],
            "reason": row[3],
            "reviewer": row[4],
            "created_at": row[5],
        }
        for row in conn.execute(
            "SELECT paper_id, stage, decision, reason, reviewer, created_at "
            "FROM screening_decisions WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
    ]
    adjudications = [
        {
            "paper_id": row[0],
            "decision": row[1],
            "reason": row[2],
            "editor": row[3],
            "created_at": row[4],
        }
        for row in conn.execute(
            "SELECT paper_id, decision, reason, editor, created_at "
            "FROM adjudications WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
    ]
    evidence = [
        {
            "paper_id": row[0],
            "design": row[1],
            "sample_size": row[2],
            "intervention": row[3],
            "comparator": row[4],
            "outcomes": row[5],
            "effect": row[6],
            "source_sentence": row[7],
        }
        for row in conn.execute(
            "SELECT paper_id, design, sample_size, intervention, comparator, outcomes, "
            "effect, source_sentence FROM evidence_rows WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
    ]
    rob = [
        {"paper_id": row[0], "domain": row[1], "judgement": row[2], "support": row[3]}
        for row in conn.execute(
            "SELECT paper_id, domain, judgement, support FROM risk_of_bias "
            "WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
    ]
    members = systematic.members(conn, project_id)
    events = systematic.list_events(conn, project_id, limit=1000)
    return {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": project.get("name"),
            "field_text": project.get("field_text"),
            "pico": project.get("pico") or {},
        },
        "papers": papers,
        "screening": screening,
        "adjudications": adjudications,
        "evidence": evidence,
        "risk_of_bias": rob,
        "members": members,
        "events": events,
    }


def import_project(conn: sqlite3.Connection, data: Dict, owner: str) -> Dict:
    project = data.get("project") or {}
    project_id = systematic.create_project(
        conn,
        project.get("name") or "Imported project",
        project.get("field_text") or "",
        project.get("pico") or {},
        owner=owner,
    )
    papers = data.get("papers") or []
    if papers:
        systematic.add_papers(conn, project_id, papers)
    for row in data.get("screening") or []:
        systematic.screen(
            conn,
            project_id,
            row.get("paper_id", ""),
            row.get("decision", ""),
            row.get("reason", ""),
            row.get("reviewer", ""),
            row.get("stage", "title_abstract"),
        )
    for row in data.get("adjudications") or []:
        systematic.adjudicate(
            conn,
            project_id,
            row.get("paper_id", ""),
            row.get("decision", ""),
            row.get("reason", ""),
            row.get("editor", ""),
        )
    for row in data.get("evidence") or []:
        systematic.add_evidence(
            conn,
            project_id,
            row.get("paper_id", ""),
            {key: row.get(key, "") for key in (
                "design", "sample_size", "intervention", "comparator",
                "outcomes", "effect", "source_sentence",
            )},
        )
    for row in data.get("risk_of_bias") or []:
        conn.execute(
            "INSERT INTO risk_of_bias (project_id, paper_id, domain, judgement, support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                row.get("paper_id", ""),
                row.get("domain", ""),
                row.get("judgement", ""),
                row.get("support", ""),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    for row in data.get("members") or []:
        systematic.add_member(conn, project_id, row.get("member", ""), row.get("role", "reviewer"))
    conn.commit()
    return {
        "project_id": project_id,
        "papers": len(papers),
        "screening": len(data.get("screening") or []),
        "evidence": len(data.get("evidence") or []),
    }
