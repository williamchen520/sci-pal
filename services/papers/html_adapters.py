"""Publisher-specific HTML section normalization."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

NATURE_SKIP = {"inline recommendations", "supplementary information"}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def detect_publisher(source_url: str, html: str = "") -> str:
    url = (source_url or "").lower()
    if "nature.com" in url or re.search(r"/articles/s415\d", url):
        return "nature"
    if "ncbi.nlm.nih.gov/pmc" in url or "pmc.ncbi.nlm.nih.gov" in url:
        return "pmc"
    return "other"


def _direct_paragraphs(section) -> list[str]:
    paragraphs: list[str] = []
    for node in section.find_all("p"):
        if node.find_parent("section") is not section and node.find_parent("div", class_="sec") is not section:
            continue
        text = _text(node.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)
    return paragraphs


def _section_title(section) -> str:
    classes = section.get("class") or []
    if "abstract" in classes:
        return "Abstract"
    value = section.get("data-title")
    if value:
        return _text(value)
    heading = section.find(["h1", "h2", "h3", "h4"])
    return _text(heading.get_text(" ", strip=True)) if heading else ""


def nature_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    sections = []
    for section in soup.select("section[data-title]"):
        title = _section_title(section)
        if not title or title.lower() in NATURE_SKIP:
            continue
        paragraphs = _direct_paragraphs(section)
        if paragraphs:
            sections.append({"title": title, "paragraphs": paragraphs})
    return sections


def pmc_sections(soup: BeautifulSoup) -> list[dict[str, Any]]:
    sections = []
    for section in soup.select("section, div.sec"):
        title = _section_title(section)
        if not title and not section.find("p"):
            continue
        paragraphs = _direct_paragraphs(section)
        if paragraphs:
            sections.append({"title": title or "(untitled)", "paragraphs": paragraphs})
    return sections


def normalize_sections(
    soup: BeautifulSoup, publisher: str, fallback: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if publisher == "nature":
        sections = nature_sections(soup)
    elif publisher == "pmc":
        sections = pmc_sections(soup)
    else:
        sections = []
    return sections or fallback
