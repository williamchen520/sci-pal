"""JATS XML parser (PMC / Europe PMC full text).

Unlike PDF parsing, JATS carries its own structure:

* ``<sec>`` nesting is the section tree (no need to reconstruct from text);
* ``<ref-list>`` is the reference list;
* ``<fig>`` / ``<table-wrap>`` are figures/tables;
* ``<xref ref-type="bibr|fig|table" rid="...">`` is an authoritative
  sentence-level link — no regex guessing.

The parser returns plain dictionaries so the importer can write the same
tables used by the PDF pipeline (sections / paragraphs / citations / figures /
tables / sentences / sentence_links), but without bbox (XML has no coordinates).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s;,\]\)\"<>]+")
SKIP_TAGS = {"title", "label", "caption", "table", "graphic", "alternatives"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return re.sub(r"\s+", " ", "".join(elem.itertext())).strip()


def _text_with_xrefs(elem: ET.Element) -> tuple[str, List[Dict[str, Any]]]:
    """Extract text and xref offsets (offset = char index in the normalized text)."""
    parts: List[str] = []
    xrefs: List[Dict[str, Any]] = []
    pos = 0

    def walk(node: ET.Element) -> None:
        nonlocal pos
        if node.text:
            parts.append(node.text)
            pos += len(node.text)
        for child in node:
            local = _local(child.tag)
            if local == "xref":
                xrefs.append(
                    {
                        "rid": child.get("rid", ""),
                        "ref_type": child.get("ref-type", ""),
                        "offset": pos,
                    }
                )
            walk(child)
            if child.tail:
                parts.append(child.tail)
                pos += len(child.tail)

    walk(elem)
    raw = "".join(parts)
    out: List[str] = []
    index_map: Dict[int, int] = {}
    last_space = False
    for index, char in enumerate(raw):
        if char.isspace():
            if not last_space and out:
                out.append(" ")
            last_space = True
        else:
            out.append(char)
            last_space = False
        index_map[index] = len(out) - 1
    text = "".join(out).strip()
    mapped = []
    for xref in xrefs:
        start = index_map.get(xref["offset"], len(text))
        mapped.append({**xref, "offset": min(start, max(len(text) - 1, 0))})
    return text, mapped


def _meta(article: ET.Element) -> Dict[str, Any]:
    front = article.find(".//front")
    meta: Dict[str, Any] = {}
    if front is None:
        return meta
    title = front.find(".//article-title")
    meta["title"] = _text(title)
    journal = front.find(".//journal-title")
    meta["journal"] = _text(journal)
    doi = None
    for aid in front.findall(".//article-id"):
        if (aid.get("pub-id-type") or "").lower() == "doi":
            doi = _text(aid)
            break
    meta["doi"] = doi
    year = front.find(".//pub-date/year")
    meta["year"] = _text(year) or None
    authors = []
    for contrib in front.findall(".//contrib"):
        surname = _text(contrib.find(".//surname"))
        given = _text(contrib.find(".//given-names"))
        if surname:
            authors.append(f"{given} {surname}".strip())
    meta["authors"] = authors
    abstract = " ".join(_text(a) for a in front.findall(".//abstract"))
    meta["abstract"] = abstract[:4000]
    keywords = [_text(k) for k in front.findall(".//kwd")]
    meta["keywords"] = [k for k in keywords if k]
    return meta


def parse_jats(xml_text: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_text)
    article = root if _local(root.tag) == "article" else root.find(".//article")
    if article is None:
        raise ValueError("no <article> element")

    result: Dict[str, Any] = {
        "metadata": _meta(article),
        "sections": [],
        "paragraphs": [],
        "figures": [],
        "tables": [],
        "references": [],
    }

    body = article.find(".//body")
    para_seq = 0

    def walk_sec(sec: ET.Element, path: List[str], parent_id: str | None) -> None:
        nonlocal para_seq
        title_elem = sec.find("title")
        title = _text(title_elem)
        current_path = path + [title] if title else path

        section_id = None
        if title:
            section_id = f"sec_{len(result['sections']) + 1:04d}"
            result["sections"].append(
                {
                    "section_id": section_id,
                    "parent_id": parent_id,
                    "level": len(current_path),
                    "title": title,
                    "path": current_path,
                }
            )
        for child in sec:
            local = _local(child.tag)
            if local == "sec":
                walk_sec(child, current_path, section_id or parent_id)
            elif local in ("p", "list", "disp-quote", "statement"):
                text, xrefs = _text_with_xrefs(child)
                if text:
                    result["paragraphs"].append(
                        {
                            "section_id": section_id,
                            "path": current_path,
                            "sequence": para_seq,
                            "text": text,
                            "xrefs": xrefs,
                        }
                    )
                    para_seq += 1

    if body is not None:
        for child in body:
            local = _local(child.tag)
            if local == "sec":
                walk_sec(child, [], None)
            elif local in ("p", "list", "disp-quote", "statement"):
                text, xrefs = _text_with_xrefs(child)
                if text:
                    result["paragraphs"].append(
                        {
                            "section_id": None,
                            "path": [],
                            "sequence": para_seq,
                            "text": text,
                            "xrefs": xrefs,
                        }
                    )
                    para_seq += 1

    # figures / tables
    for fig in article.findall(".//fig"):
        fid = fig.get("id", "")
        result["figures"].append(
            {
                "id": fid,
                "label": _text(fig.find("label")),
                "caption": _text(fig.find("caption")),
                "graphic": (fig.find(".//graphic").get("xlink:href", "")
                            if fig.find(".//graphic") is not None else ""),
            }
        )
    for table in article.findall(".//table-wrap"):
        tid = table.get("id", "")
        result["tables"].append(
            {
                "id": tid,
                "label": _text(table.find("label")),
                "caption": _text(table.find("caption")),
                "markdown": _text(table),
            }
        )

    # references
    for ref in article.findall(".//ref-list/ref"):
        rid = ref.get("id", "")
        mixed = ref.find("mixed-citation")
        text = _text(mixed) if mixed is not None else _text(ref)
        doi_match = DOI_RE.search(text or "")
        result["references"].append(
            {
                "id": rid,
                "text": text[:1000],
                "doi": doi_match.group(0).rstrip(".,;") if doi_match else None,
                "title": _text(ref.find(".//article-title")),
                "year": _text(ref.find(".//year")) or None,
            }
        )

    return result


def parse_file(path: Path | str) -> Dict[str, Any]:
    return parse_jats(Path(path).read_text(encoding="utf-8", errors="replace"))
