"""Seed scipal_dev with a tiny, repeatable fixture."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db.pg_pool import pg_connection

USER = "user_dev"
WS = "ws_default"
PAPERS = [
    {
        "paper_id": "paper_dev_hcc_001",
        "title": "Dev fixture: ICI rechallenge in hepatocellular carcinoma",
        "doi": "10.0000/dev.hcc.001",
        "paras": [
            ("sec_dev_001", "Introduction", 0, "ICI rechallenge after discontinuation is a potential therapeutic strategy in hepatocellular carcinoma."),
            ("sec_dev_001", "Introduction", 1, "Four rechallenge strategies combine agents used in initial and subsequent treatment."),
            ("sec_dev_002", "Methods", 2, "We retrospectively reviewed patients who received an immune checkpoint inhibitor rechallenge."),
            ("sec_dev_002", "Results", 3, "The objective response rate was higher in the rechallenge group than in the control group."),
        ],
    },
    {
        "paper_id": "paper_dev_crc_002",
        "title": "Dev fixture: MSI-H colorectal cancer immunotherapy",
        "doi": "10.0000/dev.crc.002",
        "paras": [
            ("sec_dev_101", "Introduction", 0, "Microsatellite instability-high colorectal cancer responds to immune checkpoint blockade."),
            ("sec_dev_101", "Introduction", 1, "Mismatch repair deficiency is the key predictive biomarker."),
            ("sec_dev_102", "Results", 2, "Objective responses were observed in patients with MSI-H tumors."),
            ("sec_dev_102", "Discussion", 3, "Resistance mechanisms include acquired mutations in antigen presentation."),
        ],
    },
]


def _pg():
    dsn = os.environ.get("SCIPAL_PG_DEV_OWNER_DSN", "").strip()
    if not dsn:
        raise SystemExit("SCIPAL_PG_DEV_OWNER_DSN is required")
    return pg_connection(dsn)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print(f"would seed user={USER} workspace={WS} papers={len(PAPERS)}")
        return 0

    pg = _pg()
    try:
        pg.execute("DELETE FROM paragraph_embeddings WHERE paper_id LIKE 'paper_dev_%'")
        pg.execute("DELETE FROM sentences WHERE paper_id LIKE 'paper_dev_%'")
        pg.execute("DELETE FROM paragraphs WHERE paper_id LIKE 'paper_dev_%'")
        pg.execute("DELETE FROM sections WHERE paper_id LIKE 'paper_dev_%'")
        pg.execute("DELETE FROM library_main.paper_documents WHERE paper_id LIKE 'paper_dev_%'")
        pg.execute("DELETE FROM library_main.documents WHERE work_id LIKE 'work_dev_%'")
        pg.execute("DELETE FROM catalog.works WHERE work_id LIKE 'work_dev_%'")
        pg.execute("DELETE FROM papers WHERE paper_id LIKE 'paper_dev_%'")
        pg.execute("DELETE FROM memberships WHERE user_id=%s", (USER,))
        pg.execute("DELETE FROM workspaces WHERE workspace_id=%s", (WS,))
        pg.execute("DELETE FROM users WHERE user_id=%s", (USER,))

        pg.execute(
            "INSERT INTO catalog.libraries "
            "(library_id, name, scope, source_type, schema_name, status) "
            "VALUES ('library_main','SciPal main library','main','mixed','library_main','active') "
            "ON CONFLICT (library_id) DO NOTHING"
        )
        pg.execute(
            "INSERT INTO users (user_id, username, display_name, status, is_admin) "
            "VALUES (%s,'dev','Dev User','active',0) ON CONFLICT (user_id) DO NOTHING",
            (USER,),
        )
        pg.execute(
            "INSERT INTO workspaces (workspace_id, name, owner_user_id) "
            "VALUES (%s,'Development',%s) ON CONFLICT (workspace_id) DO NOTHING",
            (WS, USER),
        )
        pg.execute(
            "INSERT INTO memberships (workspace_id, user_id, role, status) "
            "VALUES (%s,%s,'owner','active') ON CONFLICT DO NOTHING",
            (WS, USER),
        )

        for paper in PAPERS:
            pid = paper["paper_id"]
            pg.execute(
                "INSERT INTO papers (paper_id, filename, title, doi, year, workspace_id, parse_engine, total_paragraphs) "
                "VALUES (%s,%s,%s,%s,2026,%s,'dev',%s)",
                (pid, pid + ".xml", paper["title"], paper["doi"], WS, len(paper["paras"])),
            )
            for sid, title, seq, _ in paper["paras"]:
                pg.execute(
                    "INSERT INTO sections (section_id, paper_id, parent_id, level, title, seq, path, depth) "
                    "VALUES (%s,%s,NULL,1,%s,%s,%s,1) ON CONFLICT (section_id) DO NOTHING",
                    (sid, pid, title, seq, title),
                )
            for index, (sid, _title, seq, text) in enumerate(paper["paras"]):
                para_id = f"{pid}_p{index:03d}"
                sent_id = f"{para_id}_s000"
                pg.execute(
                    "INSERT INTO paragraphs (para_id, paper_id, section_id, section_level1, text, sequence, parse_engine) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'dev')",
                    (para_id, pid, sid, _title, text, seq),
                )
                pg.execute(
                    "INSERT INTO sentences (sentence_id, para_id, paper_id, section_id, text, sequence, char_start, char_end) "
                    "VALUES (%s,%s,%s,%s,%s,0,0,%s)",
                    (sent_id, para_id, pid, sid, text, len(text)),
                )
                pg.execute(
                    "INSERT INTO paragraph_embeddings (para_id, paper_id, embedding) "
                    "VALUES (%s,%s,%s::vector) ON CONFLICT (para_id) DO NOTHING",
                    (para_id, pid, "[" + ",".join(["0"] * 768) + "]"),
                )
            work_id = "work_dev_" + pid[-3:]
            pg.execute(
                "INSERT INTO catalog.works (work_id, primary_doi, title, year) VALUES (%s,%s,%s,2026) "
                "ON CONFLICT (work_id) DO NOTHING",
                (work_id, paper["doi"], paper["title"]),
            )
            doc_id = "doc_dev_" + pid[-3:]
            pg.execute(
                "INSERT INTO library_main.documents "
                "(document_id, work_id, library_id, source_type, source_path, sha256, parser) "
                "VALUES (%s,%s,'library_main','xml',%s,'devsha','dev') ON CONFLICT (document_id) DO NOTHING",
                (doc_id, work_id, pid + ".xml"),
            )
            pg.execute(
                "INSERT INTO library_main.paper_documents (paper_id, document_id) VALUES (%s,%s) "
                "ON CONFLICT (paper_id) DO UPDATE SET document_id=EXCLUDED.document_id",
                (pid, doc_id),
            )
        pg.commit()
        print("seed committed")
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
