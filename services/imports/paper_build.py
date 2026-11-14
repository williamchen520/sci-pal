"""Build a parsed JATS/HTML paper into the canonical corpus."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import psycopg

from services.papers.sentences import build_for_paper


class BuildError(RuntimeError):
    """The parsed paper cannot be built."""


def _dsn() -> str:
    value = (
        os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )
    if not value:
        raise BuildError("tenant corpus writer DSN is not configured")
    return value


def paper_id_for(item: dict[str, Any]) -> str:
    key = f"{item.get('source_kind')}|{item.get('source_uri')}|{item.get('content_hash')}"
    return "paper_import_" + hashlib.sha1(key.encode()).hexdigest()[:12]


def _paragraph_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in payload.get("sections") or []:
        title = str(section.get("title") or "")
        for text in section.get("paragraphs") or []:
            text = str(text).strip()
            if text:
                rows.append(
                    {
                        "section_path": title,
                        "section_level1": "body",
                        "section_level2": title,
                        "text": text,
                    }
                )
    if not rows:
        raise BuildError("parsed paper has no paragraphs")
    return rows


def build_paper(
    paper_id: str,
    payload: dict[str, Any],
    *,
    source_kind: str,
    source_uri: str,
    dsn: str | None = None,
) -> dict[str, Any]:
    rows = _paragraph_rows(payload)
    dsn = dsn or _dsn()
    title = str(payload.get("title") or "")
    with psycopg.connect(dsn) as conn:
        conn.execute(
            """
            INSERT INTO papers
              (paper_id,title,doi,journal,filename,parse_engine,total_paragraphs,acquisition)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'import')
            ON CONFLICT (paper_id) DO UPDATE SET
              title=EXCLUDED.title,
              parse_engine=EXCLUDED.parse_engine,
              total_paragraphs=EXCLUDED.total_paragraphs
            """,
            (
                paper_id,
                title,
                str(payload.get("doi") or ""),
                str(payload.get("journal") or ""),
                source_uri,
                f"import-{source_kind}",
                len(rows),
            ),
        )
        source_id = "src_" + hashlib.sha1(
            f"{paper_id}:{source_kind}:{source_uri}".encode()
        ).hexdigest()[:16]
        conn.execute(
            """
            INSERT INTO paper_sources
              (source_id,paper_id,source_kind,source_uri,parser,parser_version,is_primary,metadata)
            VALUES (%s,%s,%s,%s,%s,'v1',true,%s::jsonb)
            ON CONFLICT (paper_id,source_kind,source_uri) DO NOTHING
            """,
            (
                source_id,
                paper_id,
                source_kind,
                source_uri,
                "import",
                json.dumps({"imported": True}, ensure_ascii=False),
            ),
        )
        conn.execute("DELETE FROM sentences WHERE paper_id=%s", (paper_id,))
        conn.execute("DELETE FROM paragraphs WHERE paper_id=%s", (paper_id,))
        for index, row in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO paragraphs
                  (para_id,paper_id,section_level1,section_level2,section_path,text,
                   sequence,parse_engine)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'import')
                """,
                (
                    f"{paper_id}_para_{index:04d}",
                    paper_id,
                    row["section_level1"],
                    row["section_level2"],
                    row["section_path"],
                    row["text"],
                    index,
                ),
            )
        conn.commit()
    sentences = build_for_paper(paper_id=paper_id, dsn=dsn, replace=True)
    return {
        "paper_id": paper_id,
        "paragraphs": len(rows),
        "sentences": sentences.get("sentences", 0),
        "source_id": source_id,
    }
