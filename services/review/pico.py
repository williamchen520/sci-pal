"""Rule-based PICO extraction for systematic review projects."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Dict, List, Optional

POPULATION = re.compile(
    r"(hepatocellular carcinoma|HCC|colorectal cancer|breast cancer|lung cancer|"
    r"carcinoma|cancer|tumou?r|patients with [a-z ]{3,40})",
    re.IGNORECASE,
)
INTERVENTION = re.compile(
    r"(immune checkpoint inhibitors?|ICI|anti-PD-?1|anti-PD-L1|nivolumab|pembrolizumab|"
    r"atezolizumab|ipilimumab|rechallenge|targeted therapy|chemotherapy|[a-z]+mab)",
    re.IGNORECASE,
)
COMPARATOR = re.compile(
    r"(placebo|standard of care|standard therapy|chemotherapy|initial ICI|"
    r"comparator|versus|vs\.?)",
    re.IGNORECASE,
)
OUTCOME = re.compile(
    r"(overall survival|OS|progression-free survival|PFS|objective response rate|ORR|"
    r"response rate|disease control rate|DCR|mortality|toxicity)",
    re.IGNORECASE,
)


def _first(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text or "")
    return match.group(1).strip() if match else ""


def extract(text: str) -> Dict[str, str]:
    return {
        "population": _first(POPULATION, text),
        "intervention": _first(INTERVENTION, text),
        "comparator": _first(COMPARATOR, text),
        "outcome": _first(OUTCOME, text),
    }


def auto_pico(conn: sqlite3.Connection, project_id: str) -> Dict[str, str]:
    row = conn.execute(
        "SELECT field_text, pico_json FROM review_projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if not row:
        raise KeyError("project not found")
    text_parts: List[str] = [row[0] or ""]
    for title, abstract in conn.execute(
        "SELECT p.title, p.abstract FROM review_project_papers rp "
        "JOIN papers p ON p.paper_id = rp.paper_id WHERE rp.project_id = ?",
        (project_id,),
    ):
        text_parts.append(title or "")
        text_parts.append(abstract or "")
    extracted = extract("\n".join(text_parts))
    existing = json.loads(row[1] or "{}")
    for key, value in extracted.items():
        if value and not existing.get(key):
            existing[key] = value
    conn.execute(
        "UPDATE review_projects SET pico_json = ? WHERE project_id = ?",
        (json.dumps(existing, ensure_ascii=False), project_id),
    )
    conn.commit()
    return existing
