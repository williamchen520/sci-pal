"""PDF parse pipeline: Docling primary + GROBID enrichment + MinerU fallback.

The three engines are complementary, not redundant:

* Docling  — body text, section hierarchy, figures, tables (digital PDFs)
* GROBID   — header metadata and structured references (enrichment only)
* MinerU   — OCR / complex layouts, used when Docling's body fails a quality gate

Every parse records which engine produced which field
(``result["provenance"]``) and the decision reason, so downstream code can
tell "Docling text + GROBID refs" from "MinerU fallback".
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .docling_parser import DoclingParser

try:  # GROBID is optional
    from .grobid_parser import GrobidParser

    _GROBID_CLASS = GrobidParser
except Exception:  # noqa: BLE001
    _GROBID_CLASS = None

CONSORTIUM_SUFFIXES = (
    " research team", " study group", " study team", " consortium",
    " collaboration", " network", " initiative", " project",
    " group", " working group",
)


def is_grobid_title_suspicious(title: str) -> tuple:
    """Return (suspicious, reason) for a GROBID title candidate."""
    if not title:
        return True, "empty title"
    text = title.strip()
    alpha = [c for c in text if c.isalpha()]
    if len(alpha) >= 8:
        upper_ratio = sum(1 for c in alpha if c.isupper()) / len(alpha)
        if upper_ratio > 0.85:
            return True, f"all-caps (upper ratio {upper_ratio:.0%})"
    lower = text.lower()
    for suffix in CONSORTIUM_SUFFIXES:
        if lower.endswith(suffix):
            return True, f"ends with consortium suffix '{suffix}'"
    if text.endswith("(") or text.endswith("-") or text.endswith("—"):
        return True, "truncated (ends with open bracket/dash)"
    if len(text) < 10:
        return True, f"too short ({len(text)} chars)"
    return False, ""


def journal_from_doi(doi: str) -> Optional[str]:
    if not doi:
        return None
    doi_lower = doi.lower()
    mapping = {
        "10.1038/s41586": "Nature",
        "10.1038/s41591": "Nature Medicine",
        "10.1038/s41587": "Nature Biotechnology",
        "10.1038/s41467": "Nature Communications",
        "10.1016/j.cell": "Cell",
        "10.1016/j.molcel": "Molecular Cell",
        "10.1016/j.ccell": "Cancer Cell",
        "10.1126/science": "Science",
        "10.1126/sciadv": "Science Advances",
        "10.1172/jci": "Journal of Clinical Investigation",
        "10.1084/jem": "Journal of Experimental Medicine",
    }
    for prefix, journal in mapping.items():
        if doi_lower.startswith(prefix):
            return journal
    return None


@dataclass
class GateThresholds:
    """Quality gate for the Docling body result."""

    min_chars_per_page: float = 800.0
    min_paragraphs_per_page: float = 2.0
    min_sections: int = 1
    min_paragraph_chars: int = 200  # per page-ish floor used in score


@dataclass
class ParseProvenance:
    text_engine: str = "docling"
    meta_engine: str = ""
    refs_engine: str = ""
    tables_engine: str = ""
    decision: str = "primary"
    metrics: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text_engine": self.text_engine,
            "meta_engine": self.meta_engine,
            "refs_engine": self.refs_engine,
            "tables_engine": self.tables_engine,
            "decision": self.decision,
            "metrics": self.metrics,
        }


def pdf_page_count(pdf_path: str) -> int:
    try:
        import fitz  # PyMuPDF

        with fitz.open(pdf_path) as doc:
            return max(1, doc.page_count)
    except Exception:  # noqa: BLE001
        return 1


def _paragraph_text(paragraph: Dict[str, Any]) -> str:
    return str(paragraph.get("text") or paragraph.get("text_content") or "")


def _paragraph_section(paragraph: Dict[str, Any]) -> str:
    return str(
        paragraph.get("section_level1")
        or paragraph.get("section_type")
        or paragraph.get("section_title")
        or ""
    )


def body_metrics(result: Dict[str, Any], pages: int) -> Dict[str, Any]:
    paragraphs = result.get("paragraphs") or []
    chars = sum(len(_paragraph_text(p)) for p in paragraphs)
    sections = {_paragraph_section(p) for p in paragraphs if _paragraph_section(p)}
    return {
        "pages": pages,
        "paragraphs": len(paragraphs),
        "chars": chars,
        "chars_per_page": round(chars / max(pages, 1), 1),
        "paragraphs_per_page": round(len(paragraphs) / max(pages, 1), 2),
        "sections": len(sections),
        "figures": len(result.get("figures") or []),
        "tables": len(result.get("tables") or []),
        "citations": len(result.get("citations") or []),
    }


def gate_failure(metrics: Dict[str, Any], thresholds: GateThresholds) -> Optional[str]:
    """Return a human-readable reason when the body result fails the gate."""
    if metrics["chars_per_page"] < thresholds.min_chars_per_page:
        return (
            f"chars/page {metrics['chars_per_page']} < {thresholds.min_chars_per_page}"
        )
    if metrics["paragraphs_per_page"] < thresholds.min_paragraphs_per_page:
        return (
            f"paragraphs/page {metrics['paragraphs_per_page']} "
            f"< {thresholds.min_paragraphs_per_page}"
        )
    if metrics["sections"] < thresholds.min_sections:
        return f"sections {metrics['sections']} < {thresholds.min_sections}"
    return None


def quality_score(metrics: Dict[str, Any]) -> float:
    """Higher is better; used to pick between Docling and MinerU bodies."""
    return (
        metrics["chars_per_page"]
        + 120.0 * metrics["paragraphs_per_page"]
        + 60.0 * min(metrics["sections"], 8)
        + 5.0 * metrics["tables"]
        + 2.0 * metrics["figures"]
    )


class PdfParsePipeline:
    """Single entry point for PDF parsing (Docling + GROBID + MinerU)."""

    def __init__(
        self,
        *,
        docling: Any = None,
        grobid: Any = None,
        mineru: Any = None,
        thresholds: GateThresholds | None = None,
        enable_grobid: bool = True,
        enable_mineru: bool = True,
        log: Callable[[str], None] = print,
    ) -> None:
        self.thresholds = thresholds or GateThresholds()
        self.log = log
        self.docling = docling or DoclingParser()
        self._mineru = mineru
        self._mineru_enabled = enable_mineru
        self.grobid = grobid
        if grobid is None and enable_grobid and _GROBID_CLASS is not None:
            try:
                candidate = _GROBID_CLASS()
                if candidate.is_alive():
                    self.grobid = candidate
                    self.log("✅ GROBID active: will enrich metadata + references")
                else:
                    self.log("ℹ️  GROBID server not running; metadata/citations rely on Docling")
            except Exception as exc:  # noqa: BLE001
                self.log(f"⚠️  GROBID init failed: {str(exc)[:80]}")

    # ------------------------------------------------------------------
    def parse_paper(self, pdf_path: str, paper_id: str | None = None) -> Dict[str, Any]:
        if not paper_id:
            paper_id = self._generate_paper_id(pdf_path)
        pages = pdf_page_count(pdf_path)
        provenance = ParseProvenance()

        self.log(f"📝 Docling: {os.path.basename(pdf_path)}")
        result = self.docling.parse(pdf_path, paper_id)
        metrics = body_metrics(result, pages)
        provenance.metrics = dict(metrics)

        reason = gate_failure(metrics, self.thresholds)
        if reason and self._mineru_enabled:
            mineru = self._get_mineru()
            if mineru is not None:
                self.log(f"⚠️  gate failed ({reason}); trying MinerU fallback")
                try:
                    alt = mineru.parse(pdf_path, paper_id)
                    alt_metrics = body_metrics(alt, pages)
                    if quality_score(alt_metrics) > quality_score(metrics):
                        result = alt
                        metrics = alt_metrics
                        provenance.text_engine = "mineru"
                        provenance.decision = f"mineru_fallback: {reason}"
                        provenance.metrics = dict(alt_metrics)
                        self.log("✅ MinerU body accepted")
                    else:
                        provenance.decision = f"docling_kept: {reason}; mineru worse"
                        self.log("ℹ️  MinerU did not beat Docling; keeping Docling")
                except Exception as exc:  # noqa: BLE001
                    provenance.decision = f"docling_kept: {reason}; mineru error {exc}"
                    self.log(f"⚠️  MinerU fallback failed: {str(exc)[:100]}")
        elif reason:
            provenance.decision = f"docling_kept: {reason}; mineru disabled"

        # GROBID enrichment (metadata + references only)
        provenance.meta_engine = provenance.text_engine
        provenance.refs_engine = provenance.text_engine
        if self.grobid is not None:
            try:
                gres = self.grobid.parse(pdf_path, paper_id)
                if "error" not in gres:
                    self._merge_grobid(result, gres, paper_id)
                    provenance.meta_engine = "grobid"
                    if gres.get("citations"):
                        provenance.refs_engine = "grobid"
                else:
                    self.log(f"   ⚠️  GROBID parse error: {gres.get('error')}")
            except Exception as exc:  # noqa: BLE001
                self.log(f"   ⚠️  GROBID enrichment failed: {str(exc)[:100]}")

        provenance.tables_engine = provenance.text_engine

        metadata = result.setdefault("metadata", {})
        engines = {provenance.text_engine, provenance.meta_engine, provenance.refs_engine}
        metadata["parse_engine"] = "+".join(sorted(e for e in engines if e))
        metadata.setdefault("parse_status", "completed")
        result["provenance"] = provenance.as_dict()
        return result

    # ------------------------------------------------------------------
    def _get_mineru(self):
        if self._mineru is not None:
            return self._mineru
        try:
            from .mineru_parser import MinerUParser

            self._mineru = MinerUParser()
            return self._mineru
        except Exception as exc:  # noqa: BLE001
            self.log(f"ℹ️  MinerU unavailable: {str(exc)[:80]}")
            return None

    def _merge_grobid(self, result: Dict[str, Any], gres: Dict[str, Any], paper_id: str) -> None:
        grobid_meta = gres.get("metadata") or {}
        grobid_citations = gres.get("citations") or []
        current = result.setdefault("metadata", {})

        g_title = (grobid_meta.get("title") or "").strip()
        if g_title:
            suspicious, why = is_grobid_title_suspicious(g_title)
            if suspicious:
                self.log(f"   ⚠️  GROBID title rejected ({why}): {g_title[:50]!r}")
            else:
                current["title"] = g_title
        if grobid_meta.get("authors"):
            current["authors"] = grobid_meta["authors"]
        if grobid_meta.get("journal"):
            current["journal"] = grobid_meta["journal"]
        elif not current.get("journal") and grobid_meta.get("doi"):
            inferred = journal_from_doi(grobid_meta["doi"])
            if inferred:
                current["journal"] = inferred
        for key in ("doi", "year", "abstract"):
            if grobid_meta.get(key):
                current[key] = grobid_meta[key]

        if grobid_citations:
            enriched = []
            for index, ref in enumerate(grobid_citations, 1):
                item = dict(ref)
                item["citation_id"] = f"cite_{paper_id}_{index:04d}"
                item["paper_id"] = paper_id
                enriched.append(item)
            result["citations"] = enriched

    @staticmethod
    def _generate_paper_id(pdf_path: str) -> str:
        with open(pdf_path, "rb") as handle:
            file_hash = hashlib.md5(handle.read()).hexdigest()[:12]
        filename = os.path.basename(pdf_path).replace(".pdf", "")
        clean = "".join(c if c.isalnum() else "_" for c in filename)[:50]
        return f"paper_{clean}_{file_hash}"
