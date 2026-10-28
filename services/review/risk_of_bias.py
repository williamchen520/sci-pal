"""Simplified risk-of-bias assessment (RoB 2 inspired, heuristic)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List

DOMAINS = [
    "randomization",
    "deviations",
    "missing_data",
    "measurement",
    "reporting",
]
RANK = {"low": 0, "some concerns": 1, "high": 2}


def _judge(text: str) -> Dict[str, Dict[str, str]]:
    lower = (text or "").lower()
    out: Dict[str, Dict[str, str]] = {}

    if re.search(r"randomi[sz]ed|randomi[sz]ation", lower):
        out["randomization"] = {"judgement": "low", "support": "randomized design reported"}
    elif re.search(r"non-random|observational|retrospective|single-arm", lower):
        out["randomization"] = {"judgement": "high", "support": "non-randomized design"}
    else:
        out["randomization"] = {"judgement": "some concerns", "support": "method not reported"}

    if re.search(r"double-blind|placebo-controlled|sham", lower):
        out["deviations"] = {"judgement": "low", "support": "blinding reported"}
    elif re.search(r"open-label|unblinded", lower):
        out["deviations"] = {"judgement": "some concerns", "support": "open-label"}
    else:
        out["deviations"] = {"judgement": "some concerns", "support": "blinding unclear"}

    if re.search(r"lost to follow-up|missing data|withdrew|discontinu", lower):
        out["missing_data"] = {"judgement": "some concerns", "support": "attrition reported"}
    else:
        out["missing_data"] = {"judgement": "low", "support": "no obvious attrition"}

    if re.search(r"overall survival|objective response|hard endpoint|mortality", lower):
        out["measurement"] = {"judgement": "low", "support": "objective endpoint"}
    elif re.search(r"quality of life|symptom|patient-reported", lower):
        out["measurement"] = {"judgement": "some concerns", "support": "subjective endpoint"}
    else:
        out["measurement"] = {"judgement": "some concerns", "support": "endpoint unclear"}

    if re.search(r"registered|clinicaltrials\.gov|protocol|pre-registered", lower):
        out["reporting"] = {"judgement": "low", "support": "protocol/registration reported"}
    else:
        out["reporting"] = {"judgement": "some concerns", "support": "no protocol found"}

    return out


def assess(text: str) -> List[Dict[str, str]]:
    judgements = _judge(text)
    return [
        {"domain": domain, **judgements[domain]}
        for domain in DOMAINS
        if domain in judgements
    ]


def overall(rows: List[Dict[str, str]]) -> str:
    if not rows:
        return "some concerns"
    return max((row["judgement"] for row in rows), key=lambda value: RANK.get(value, 1))


def save(conn: sqlite3.Connection, project_id: str, paper_id: str, rows: List[Dict[str, str]]) -> None:
    conn.execute("DELETE FROM risk_of_bias WHERE project_id = ? AND paper_id = ?", (project_id, paper_id))
    for row in rows:
        conn.execute(
            "INSERT INTO risk_of_bias (project_id, paper_id, domain, judgement, support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                paper_id,
                row["domain"],
                row["judgement"],
                row.get("support", ""),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    conn.commit()


def list_rows(conn: sqlite3.Connection, project_id: str) -> List[Dict]:
    rows = conn.execute(
        "SELECT paper_id, domain, judgement, support FROM risk_of_bias "
        "WHERE project_id = ? ORDER BY paper_id, domain",
        (project_id,),
    ).fetchall()
    return [
        {"paper_id": row[0], "domain": row[1], "judgement": row[2], "support": row[3]}
        for row in rows
    ]
