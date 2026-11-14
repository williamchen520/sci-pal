"""Paper-lane parsing adapter (staging JSON only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from services.imports import session
from services.papers.html_parser import parse_html


class AdapterUnavailable(RuntimeError):
    """The parsed format has no adapter yet."""


def _text(node: ET.Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _first(node: ET.Element, name: str) -> ET.Element | None:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == name:
            return child
    return None


def parse_jats(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    sections = []
    for index, sec in enumerate(root.iter()):
        if sec.tag.rsplit("}", 1)[-1] != "sec":
            continue
        title = _text(_first(sec, "title"))
        paragraphs = [
            _text(p)
            for p in sec.iter()
            if p.tag.rsplit("}", 1)[-1] == "p" and _text(p)
        ]
        sections.append(
            {
                "section_id": sec.get("id") or f"sec_{index:03d}",
                "sec_type": sec.get("sec-type") or "",
                "title": title,
                "paragraphs": paragraphs,
            }
        )
    return {
        "source_kind": "jats",
        "article_type": root.get("article-type") or "",
        "title": _text(_first(root, "article-title")),
        "journal": _text(_first(root, "journal-title")),
        "sections": sections,
    }


class PaperLaneAdapter:
    def process(self, item: dict[str, Any]) -> str:
        path = Path(item.get("staged_path") or item.get("source_uri") or "")
        if not path.is_file():
            raise AdapterUnavailable("staged paper file not found")
        kind = item.get("source_kind")
        if kind == "jats":
            payload = parse_jats(path)
        elif kind == "html":
            payload = parse_html(
                path.read_bytes(), source_url=item.get("source_uri") or ""
            )
        elif kind == "pdf":
            raise AdapterUnavailable("pdf adapter pending")
        else:
            raise AdapterUnavailable(f"unsupported paper kind: {kind}")
        session.set_item_parsed(item["import_id"], item["item_id"], payload)
        return "parsed"
