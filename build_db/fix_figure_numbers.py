"""Reconcile ``figures.fig_number`` with the author's caption number.

PDF extraction numbers figures by order; the caption usually says ``Fig. 2``.
When they disagree, the caption wins and ``figures.number_conflict`` is set.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict

from build_db.mention_patterns import caption_number

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def fix(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    stats = {"checked": 0, "corrected": 0, "conflict": 0}
    try:
        rows = conn.execute(
            "SELECT fig_id, fig_number, caption, number_conflict FROM figures"
        ).fetchall()
        for fig_id, fig_number, caption, _ in rows:
            stats["checked"] += 1
            author_number = caption_number(caption or "")
            if not author_number:
                continue
            current = re.search(r"(\d+)", fig_number or "")
            current_number = current.group(1) if current else None
            if current_number == author_number:
                continue
            conn.execute(
                "UPDATE figures SET fig_number = ?, number_conflict = 1 WHERE fig_id = ?",
                (f"Fig {author_number}", fig_id),
            )
            stats["corrected"] += 1
            stats["conflict"] += 1
        conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    print(fix())
