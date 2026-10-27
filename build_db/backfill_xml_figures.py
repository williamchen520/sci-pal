"""Backfill figure rows for PMC XML papers from xml_figure_links.

XML imports did not create ``figures`` rows, so sentence-level figure mentions
had nothing to resolve against. Each ``xml_figure_links`` row gives the figure
id (``Fig1``) and the paragraph context where it is mentioned; we create a
lightweight figure record (no image file, no bbox) so the link builder can
attach sentences to ``fig_id``.

Then re-run the link builder for those papers.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def backfill(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    stats = {"figures": 0, "papers": 0}
    try:
        paper_by_pmc: Dict[str, str] = {
            str(filename)[:-4]: paper_id
            for paper_id, filename in conn.execute(
                "SELECT paper_id, filename FROM papers WHERE filename LIKE '%.xml'"
            )
        }
        inserted = set()
        for pmc_id, xml_fig_id, context in conn.execute(
            "SELECT pmc_id, fig_id, context FROM xml_figure_links"
        ):
            paper_id = paper_by_pmc.get(str(pmc_id))
            if not paper_id:
                continue
            match = re.search(r"(\d+)", str(xml_fig_id))
            if not match:
                continue
            number = match.group(1)
            fig_id = f"{paper_id}_xmlfig_{number}"
            if fig_id in inserted:
                continue
            inserted.add(fig_id)
            conn.execute(
                "INSERT OR IGNORE INTO figures "
                "(fig_id, paper_id, fig_number, caption, file_path, page, bbox) "
                "VALUES (?, ?, ?, ?, NULL, NULL, NULL)",
                (
                    fig_id,
                    paper_id,
                    f"Fig {number}",
                    (context or "")[:300],
                ),
            )
            stats["figures"] += 1
        stats["papers"] = len({pid for pid, _ in conn.execute(
            "SELECT DISTINCT paper_id, fig_id FROM figures WHERE fig_id LIKE '%_xmlfig_%'"
        )})
        conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    print(backfill())
