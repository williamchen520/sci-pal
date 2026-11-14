#!/usr/bin/env python3
"""Backfill JATS native metadata without touching canonical paragraphs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import psycopg


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(node: ET.Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _first(node: ET.Element, name: str) -> ET.Element | None:
    for child in node.iter():
        if _local(child.tag) == name:
            return child
    return None


def _sections(root: ET.Element) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = 0

    def walk(node: ET.Element, parent_path: str, depth: int) -> None:
        nonlocal order
        for child in list(node):
            if _local(child.tag) != "sec":
                walk(child, parent_path, depth)
                continue
            order += 1
            title = _text(_first(child, "title"))
            native_id = child.get("id") or f"sec_{order:03d}"
            sec_type = child.get("sec-type") or ""
            path = f"{parent_path} > {title}".strip(" >") if title else parent_path
            rows.append(
                {
                    "native_section_id": native_id,
                    "sec_type": sec_type,
                    "title": title,
                    "depth": depth,
                    "section_path": path,
                    "section_order": order,
                }
            )
            walk(child, path, depth + 1)

    walk(root, "", 1)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml-dir", default=r"G:/sciPal/documents_xml")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")

    files = sorted(Path(args.xml_dir).glob("*.xml"))
    if args.limit:
        files = files[: args.limit]

    with psycopg.connect(args.dsn) as conn:
        sources = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT split_part(source_uri, '/', 2), source_id FROM paper_sources "
                "WHERE source_kind='jats'"
            ).fetchall()
        }
        articles = 0
        section_rows = 0
        skipped = 0
        for path in files:
            paper_id = f"paper_{path.stem}"
            source_id = sources.get(path.name)
            if not source_id:
                skipped += 1
                continue
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                skipped += 1
                continue
            article_type = root.get("article-type") or ""
            journal = _text(_first(root, "journal-title"))
            title = _text(_first(root, "article-title"))
            license_node = _first(root, "license")
            license_value = _text(license_node)
            native = json.dumps(
                {"article_type": article_type, "journal_title": journal, "pmcid": path.stem},
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT INTO jats_articles
                  (source_id, paper_id, article_type, journal_title, article_title, license, native_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (source_id) DO UPDATE SET
                  article_type=EXCLUDED.article_type,
                  journal_title=EXCLUDED.journal_title,
                  article_title=EXCLUDED.article_title,
                  license=EXCLUDED.license,
                  native_json=EXCLUDED.native_json
                """,
                (source_id, paper_id, article_type, journal, title, license_value, native),
            )
            sections = _sections(root)
            conn.execute("DELETE FROM jats_sections WHERE source_id=%s", (source_id,))
            for section in sections:
                conn.execute(
                    """
                    INSERT INTO jats_sections
                      (source_id, native_section_id, sec_type, title, depth, section_path, section_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        source_id,
                        section["native_section_id"],
                        section["sec_type"],
                        section["title"],
                        section["depth"],
                        section["section_path"],
                        section["section_order"],
                    ),
                )
            articles += 1
            section_rows += len(sections)
        conn.commit()
    print(
        f"JATS_NATIVE_OK files={articles} sections={section_rows} skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
