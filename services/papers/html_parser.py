"""Parse publisher OA HTML into SciPal paper sections and code links.

This is intentionally conservative: it extracts structure, never bypasses a
paywall, and keeps the raw HTML hash for provenance.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from bs4 import BeautifulSoup


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name})
    return _text(tag.get("content")) if tag else ""


def _section_paragraphs(section) -> list[str]:
    paragraphs = []
    for node in section.find_all("p"):
        # Skip paragraphs that belong to a nested section; the nested section
        # will be emitted separately.
        if node.find_parent("section") is not section:
            continue
        text = _text(node.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)
    return paragraphs


def _canonical_links(soup: BeautifulSoup, section_title: str) -> list[str]:
    links: list[str] = []
    for section in soup.find_all("section"):
        heading = section.find("h2")
        title = _text(section.get("data-title") or (heading.get_text(" ", strip=True) if heading else ""))
        if section_title.lower() not in title.lower():
            continue
        for anchor in section.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if href and href not in links:
                links.append(href)
    return links


def _repo_links(soup: BeautifulSoup) -> list[str]:
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if re.search(r"(github\.com|gitlab\.com|bitbucket\.org|zenodo\.org|doi\.org/10\.5281)", href, re.I):
            if href not in links:
                links.append(href)
    return links


def parse_html(html: str | bytes, *, source_url: str = "") -> dict[str, Any]:
    raw = html.encode("utf-8") if isinstance(html, str) else html
    text = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    warnings: list[str] = []

    title = _meta(soup, "citation_title")
    if not title:
        h1 = soup.find("h1")
        title = _text(h1.get_text(" ", strip=True)) if h1 else ""
    doi = _meta(soup, "citation_doi")
    if not doi:
        match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", text)
        doi = match.group(0).rstrip(".,") if match else ""
    authors = [
        _text(tag.get("content"))
        for tag in soup.find_all("meta", attrs={"name": "citation_author"})
        if tag.get("content")
    ]
    journal = _meta(soup, "citation_journal_title")
    published = _meta(soup, "citation_publication_date") or _meta(soup, "citation_online_date")
    license_value = _meta(soup, "citation_license")

    sections: list[dict[str, Any]] = []
    for section in soup.find_all("section"):
        heading = section.find(["h1", "h2", "h3"])
        section_title = _text(section.get("data-title") or (heading.get_text(" ", strip=True) if heading else ""))
        paragraphs = _section_paragraphs(section)
        if not section_title and not paragraphs:
            continue
        if not paragraphs:
            continue
        sections.append({"title": section_title or "(untitled)", "paragraphs": paragraphs})

    if not sections:
        warnings.append("no section elements with paragraphs; falling back to flat paragraphs")
        paragraphs = [_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
        sections = [{"title": "Body", "paragraphs": [p for p in paragraphs if p]}]

    abstract = ""
    for section in sections:
        if section["title"].lower() == "abstract":
            abstract = " ".join(section["paragraphs"])
            break
    if not abstract:
        abstract_node = soup.select_one("#Abs1-content, section[data-title='Abstract']")
        if abstract_node:
            abstract = _text(abstract_node.get_text(" ", strip=True))

    figures = []
    for figure in soup.find_all("figure"):
        caption = _text(figure.get_text(" ", strip=True))
        image = figure.find("img")
        figures.append(
            {
                "caption": caption,
                "image": str(image.get("src") or "") if image else "",
            }
        )

    code_links = _canonical_links(soup, "Code availability")
    data_links = _canonical_links(soup, "Data availability")
    repo_links = _repo_links(soup)
    if not code_links:
        warnings.append("no Code availability section links; repo_links is heuristic")
    if not title:
        warnings.append("no title")
    if not doi:
        warnings.append("no DOI")

    return {
        "source_url": source_url,
        "source_kind": "html",
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "title": title,
        "doi": doi,
        "journal": journal,
        "published": published,
        "authors": authors,
        "license": license_value,
        "abstract": abstract,
        "sections": sections,
        "figures": figures,
        "code_links": code_links,
        "data_links": data_links,
        "repo_links": repo_links,
        "warnings": warnings,
    }
