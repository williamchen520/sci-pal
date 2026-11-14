"""Conservative import format detection."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

REPO_RE = re.compile(r"(github\.com|gitlab\.com|bitbucket\.org|zenodo\.org)", re.I)


@dataclass(frozen=True)
class Detection:
    source_kind: str
    kind: str
    confidence: float
    reason: str


def _suffix(uri: str) -> str:
    path = uri.split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
    return PurePosixPath(path).suffix.lower()


def detect(uri: str, head: bytes = b"") -> Detection:
    text = (uri or "").strip()
    if not text:
        return Detection("unknown", "unknown", 0.0, "empty uri")
    raw = head or b""
    lower = raw[:4096].lower()
    suffix = _suffix(text)

    if lower.startswith(b"%pdf-"):
        return Detection("pdf", "paper", 1.0, "pdf magic")
    if lower.startswith(b"pk\x03\x04"):
        return Detection("zip", "code", 0.9, "zip magic")
    if b"<article" in lower or b"<front" in lower and b"<body" in lower:
        return Detection("jats", "paper", 0.9, "jats root")
    if b"<!doctype html" in lower or b"<html" in lower:
        return Detection("html", "paper", 0.9, "html doctype")
    if suffix == ".pdf":
        return Detection("pdf", "paper", 0.7, "pdf extension")
    if suffix in {".html", ".htm"}:
        return Detection("html", "paper", 0.7, "html extension")
    if suffix == ".xml":
        return Detection("jats", "paper", 0.5, "xml extension; parser probe pending")
    if suffix == ".zip":
        return Detection("zip", "code", 0.7, "zip extension")
    if suffix == ".py":
        confidence = 0.8
        if raw:
            try:
                ast.parse(raw.decode("utf-8", errors="replace"))
            except SyntaxError:
                confidence = 0.4
        return Detection("python", "code", confidence, "python extension")
    if suffix == ".r":
        return Detection("r", "code", 0.9, "r extension")
    if suffix in {".rmd", ".qmd"}:
        return Detection("rmd", "code", 0.9, "rmd extension")
    if REPO_RE.search(text) or suffix == ".git":
        return Detection("repo", "code", 0.9, "repository url")
    return Detection("unknown", "unknown", 0.0, "no confident detector")
