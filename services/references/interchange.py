"""RIS / EndNote XML interchange for the review reference list.

EndNote has no public API; Mendeley's API is OAuth-only. The practical bridge for
both is file interchange, so this module reads and writes the two formats they
import/export by default.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping
from xml.etree import ElementTree


@dataclass
class Reference:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: str = ""
    doi: str = ""
    abstract: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": "; ".join(self.authors),
            "journal": self.journal,
            "year": self.year,
            "doi": self.doi,
            "abstract": self.abstract,
        }


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


# --------------------------------------------------------------------------- export


def to_ris(references: Iterable[Mapping]) -> str:
    lines: list[str] = []
    for ref in references:
        lines.append("TY  - JOUR")
        if ref.get("title"):
            lines.append(f"TI  - {_clean(ref['title'])}")
        for author in _authors(ref.get("authors")):
            lines.append(f"AU  - {author}")
        if ref.get("journal"):
            lines.append(f"JO  - {_clean(ref['journal'])}")
        if ref.get("year"):
            lines.append(f"PY  - {_clean(ref['year'])}")
        if ref.get("doi"):
            lines.append(f"DO  - {_clean(ref['doi'])}")
        if ref.get("abstract"):
            lines.append(f"AB  - {_clean(ref['abstract'])}")
        lines.append("ER  - ")
        lines.append("")
    return "\n".join(lines)


def to_endnote_xml(references: Iterable[Mapping]) -> str:
    records = []
    for ref in references:
        authors = "".join(
            f"<author>{html.escape(author)}</author>" for author in _authors(ref.get("authors"))
        )
        records.append(
            "<record>"
            '<ref-type name="Journal Article">17</ref-type>'
            f"<contributors><authors>{authors}</authors></contributors>"
            "<titles>"
            f"<title>{html.escape(_clean(ref.get('title')))}</title>"
            f"<secondary-title>{html.escape(_clean(ref.get('journal')))}</secondary-title>"
            "</titles>"
            f"<dates><year>{html.escape(_clean(ref.get('year')))}</year></dates>"
            f"<electronic-resource-num>{html.escape(_clean(ref.get('doi')))}</electronic-resource-num>"
            "</record>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<xml><records>" + "".join(records) + "</records></xml>"
    )


def _authors(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(";") if part.strip()]


# --------------------------------------------------------------------------- import


def parse_ris(text: str) -> list[Reference]:
    records: list[Reference] = []
    current: dict[str, list[str]] = {}
    last_tag = None
    for raw in str(text or "").splitlines():
        line = raw.rstrip("\r")
        match = re.match(r"^([A-Z][A-Z0-9])\s{1,2}-\s?(.*)$", line)
        if match:
            tag, value = match.group(1), match.group(2)
            if tag == "TY":
                current = {}
            elif tag == "ER":
                if current:
                    records.append(_ris_to_reference(current))
                current = {}
                last_tag = None
                continue
            current.setdefault(tag, []).append(value.strip())
            last_tag = tag
        elif last_tag and line.strip() and not line.startswith(" "):
            current[last_tag][-1] += " " + line.strip()
    if current:
        records.append(_ris_to_reference(current))
    return [record for record in records if record.title or record.doi]


def _ris_to_reference(data: dict[str, list[str]]) -> Reference:
    return Reference(
        title=_clean((data.get("TI") or data.get("T1") or [""])[0]),
        authors=[_clean(item) for item in data.get("AU", []) if _clean(item)],
        journal=_clean((data.get("JO") or data.get("JF") or data.get("JA") or [""])[0]),
        year=_clean((data.get("PY") or data.get("Y1") or [""])[0]),
        doi=_clean((data.get("DO") or [""])[0]),
        abstract=_clean((data.get("AB") or data.get("N2") or [""])[0]),
    )


def parse_endnote_xml(text: str) -> list[Reference]:
    try:
        root = ElementTree.fromstring(str(text or ""))
    except ElementTree.ParseError:
        return []
    records: list[Reference] = []
    for record in root.iter("record"):
        title = _first_text(record, "titles/title")
        journal = _first_text(record, "titles/secondary-title")
        year = _first_text(record, "dates/year")
        doi = _first_text(record, "electronic-resource-num")
        abstract = _first_text(record, "abstract")
        authors = [
            _clean(element.text or "")
            for element in record.findall(".//contributors/authors/author")
            if _clean(element.text or "")
        ]
        if title or doi:
            records.append(
                Reference(
                    title=_clean(title),
                    authors=authors,
                    journal=_clean(journal),
                    year=_clean(year),
                    doi=_clean(doi),
                    abstract=_clean(abstract),
                )
            )
    return records


def _first_text(element, path: str) -> str:
    child = element.find(path)
    return _clean("".join(child.itertext())) if child is not None else ""


def detect_format(text: str) -> str:
    stripped = str(text or "").lstrip()
    if stripped.startswith("<"):
        return "endnote_xml"
    if re.search(r"(?m)^TY\s{1,2}-", text or ""):
        return "ris"
    return "unknown"
