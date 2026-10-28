"""Systematic review helpers: project, screening, PRISMA, evidence extraction."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

DESIGN_PATTERNS = [
    ("systematic review", r"systematic review|meta-analysis"),
    ("RCT", r"randomi[sz]ed|randomi[sz]ation"),
    ("cohort", r"cohort study|retrospective cohort|prospective cohort"),
    ("case-control", r"case-control"),
    ("single-arm", r"single-arm|single arm"),
    ("review", r"narrative review|review"),
]
SAMPLE_RE = re.compile(r"(?:n\s*=\s*)?(\d{2,6})\s+(?:patients|participants|subjects|cases|adults)")
EFFECT_RE = re.compile(r"(HR|OR|RR)\s*[=:]?\s*[\d.]+|(\d{1,3}(?:\.\d+)?)\s?%")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(
    conn: sqlite3.Connection,
    name: str,
    field_text: str = "",
    pico: Optional[Dict[str, str]] = None,
    owner: str = "default",
) -> str:
    project_id = "rev_" + uuid.uuid4().hex[:10]
    conn.execute(
        "INSERT INTO review_projects "
        "(project_id, owner, name, field_text, pico_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            project_id,
            owner,
            name,
            field_text,
            json.dumps(pico or {}, ensure_ascii=False),
            now(),
        ),
    )
    conn.commit()
    return project_id


def get_project(conn: sqlite3.Connection, project_id: str) -> Optional[Dict]:
    row = conn.execute(
        "SELECT project_id, owner, name, field_text, pico_json "
        "FROM review_projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "project_id": row[0],
        "owner": row[1],
        "name": row[2],
        "field_text": row[3],
        "pico": json.loads(row[4] or "{}"),
    }


def list_projects(conn: sqlite3.Connection, owner: str = "default") -> List[Dict]:
    rows = conn.execute(
        "SELECT project_id, name, field_text, pico_json FROM review_projects "
        "WHERE owner = ? ORDER BY created_at DESC",
        (owner,),
    ).fetchall()
    return [
        {
            "project_id": row[0],
            "name": row[1],
            "field_text": row[2],
            "pico": json.loads(row[3] or "{}"),
        }
        for row in rows
    ]


def add_papers(conn: sqlite3.Connection, project_id: str, paper_ids: List[str]) -> int:
    for paper_id in paper_ids:
        conn.execute(
            "INSERT OR IGNORE INTO review_project_papers (project_id, paper_id, added_at) "
            "VALUES (?, ?, ?)",
            (project_id, paper_id, now()),
        )
    conn.commit()
    return len(paper_ids)


def screen(
    conn: sqlite3.Connection,
    project_id: str,
    paper_id: str,
    decision: str,
    reason: str = "",
    reviewer: str = "",
    stage: str = "title_abstract",
) -> None:
    conn.execute(
        "INSERT INTO screening_decisions "
        "(project_id, paper_id, stage, decision, reason, reviewer, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, paper_id, stage, decision, reason, reviewer, now()),
    )
    conn.commit()


def prisma(conn: sqlite3.Connection, project_id: str) -> Dict[str, int]:
    identified = conn.execute(
        "SELECT COUNT(*) FROM review_project_papers WHERE project_id = ?", (project_id,)
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT decision, COUNT(*) FROM ("
        "  SELECT paper_id, decision, ROW_NUMBER() OVER ("
        "    PARTITION BY paper_id ORDER BY id DESC"
        "  ) AS rn FROM screening_decisions WHERE project_id = ?"
        ") WHERE rn = 1 GROUP BY decision",
        (project_id,),
    ).fetchall()
    counts = {decision: count for decision, count in rows}
    included = counts.get("include", 0)
    excluded = counts.get("exclude", 0)
    return {
        "identified": identified,
        "screened": sum(counts.values()),
        "included": included,
        "excluded": excluded,
        "pending": max(identified - included - excluded, 0),
    }


def conflicts(conn: sqlite3.Connection, project_id: str, stage: str = "title_abstract") -> List[Dict]:
    rows = conn.execute(
        "SELECT paper_id, reviewer, decision, reason FROM ("
        "  SELECT paper_id, reviewer, decision, reason, ROW_NUMBER() OVER ("
        "    PARTITION BY paper_id, reviewer ORDER BY id DESC"
        "  ) AS rn FROM screening_decisions "
        "  WHERE project_id = ? AND stage = ? AND reviewer != ''"
        ") WHERE rn = 1 ORDER BY paper_id",
        (project_id, stage),
    ).fetchall()
    by_paper: Dict[str, Dict[str, str]] = {}
    for paper_id, reviewer, decision, reason in rows:
        by_paper.setdefault(paper_id, {})[reviewer] = decision
    return [
        {"paper_id": paper_id, "decisions": decisions}
        for paper_id, decisions in by_paper.items()
        if len(set(decisions.values())) > 1
    ]


def extract_evidence(paper: Dict[str, Any], pico: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    text = f"{paper.get('title') or ''}. {paper.get('abstract') or ''}"
    lower = text.lower()
    design = "unknown"
    for label, pattern in DESIGN_PATTERNS:
        if re.search(pattern, lower):
            design = label
            break
    sample = SAMPLE_RE.search(text)
    effect = EFFECT_RE.search(text)
    pico = pico or {}
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 40]
    outcome_sentence = next(
        (s for s in sentences if re.search(r"outcome|endpoint|response|survival|efficacy", s, re.I)),
        sentences[0] if sentences else "",
    )
    return {
        "design": design,
        "sample_size": sample.group(1) if sample else "",
        "intervention": pico.get("intervention", ""),
        "comparator": pico.get("comparator", ""),
        "outcomes": outcome_sentence[:300],
        "effect": effect.group(0) if effect else "",
        "source_sentence": outcome_sentence[:300],
    }


def add_evidence(conn: sqlite3.Connection, project_id: str, paper_id: str, row: Dict[str, str]) -> None:
    conn.execute(
        "INSERT INTO evidence_rows "
        "(project_id, paper_id, design, sample_size, intervention, comparator, "
        " outcomes, effect, source_sentence, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            paper_id,
            row.get("design"),
            row.get("sample_size"),
            row.get("intervention"),
            row.get("comparator"),
            row.get("outcomes"),
            row.get("effect"),
            row.get("source_sentence"),
            now(),
        ),
    )
    conn.commit()


def list_evidence(conn: sqlite3.Connection, project_id: str) -> List[Dict]:
    rows = conn.execute(
        "SELECT paper_id, design, sample_size, intervention, comparator, outcomes, effect "
        "FROM evidence_rows WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    return [
        {
            "paper_id": row[0],
            "design": row[1],
            "sample_size": row[2],
            "intervention": row[3],
            "comparator": row[4],
            "outcomes": row[5],
            "effect": row[6],
        }
        for row in rows
    ]


def evidence_csv(conn: sqlite3.Connection, project_id: str) -> str:
    rows = list_evidence(conn, project_id)
    buffer = io.StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def add_from_watch(conn: sqlite3.Connection, project_id: str, run_id: int) -> int:
    papers = [
        row[0]
        for row in conn.execute(
            "SELECT paper_id FROM watch_items WHERE run_id = ? AND paper_id IS NOT NULL",
            (run_id,),
        ).fetchall()
    ]
    if papers:
        add_papers(conn, project_id, papers)
    return len(papers)
