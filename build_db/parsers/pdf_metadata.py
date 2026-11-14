"""PDF title fallback when GROBID metadata is unavailable."""

from __future__ import annotations

import re
from pathlib import Path


def extract_pdf_title(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        if doc.page_count == 0:
            return ""
        page = doc[0]
        spans: list[tuple[float, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = str(span.get("text") or "").strip()
                    if text:
                        spans.append((float(span.get("size") or 0), text))
        if not spans:
            return ""
        # Prefer pypdf document metadata when present.
        try:
            from pypdf import PdfReader

            meta = PdfReader(str(path)).metadata or {}
            metadata_title = str(meta.get("/Title") or "").strip()
            if metadata_title and len(metadata_title) >= 10:
                return _clean(metadata_title)
        except Exception:  # noqa: BLE001
            pass
        max_size = max(size for size, _ in spans)
        lines = [
            text
            for size, text in spans
            if size >= max_size - 0.6 and len(text) >= 2
        ]
        return _clean(" ".join(lines))
    except Exception:  # noqa: BLE001
        return ""


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    for prefix in ("Article ", "ARTICLE ", "Open Access ", "OPEN "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.strip(" -|")[:500]
