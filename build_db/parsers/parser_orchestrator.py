"""Parser Orchestrator (compatibility wrapper).

The real pipeline lives in :mod:`build_db.parsers.pipeline`:
Docling (body) + GROBID (metadata/references) + MinerU (quality fallback).

``ParserOrchestrator`` is kept as the public entry point used by the API and
download paths; it simply delegates so old imports keep working.
"""

from __future__ import annotations

from typing import Any, Dict

from .pipeline import (  # re-exported for backward compatibility
    GateThresholds,
    PdfParsePipeline,
    is_grobid_title_suspicious,
    journal_from_doi,
)


class ParserOrchestrator:
    """Thin wrapper around :class:`PdfParsePipeline`."""

    def __init__(self, pipeline: PdfParsePipeline | None = None, **kwargs: Any) -> None:
        self.pipeline = pipeline or PdfParsePipeline(**kwargs)

    def parse_paper(self, pdf_path: str, paper_id: str | None = None) -> Dict[str, Any]:
        return self.pipeline.parse_paper(pdf_path, paper_id)
