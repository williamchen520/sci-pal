"""Code-lane parsing adapter (staging JSON only, never executes code)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from code_rag.parsers import parse_python, parse_r, parse_rmd
from services.imports import session


class AdapterUnavailable(RuntimeError):
    """The code source has no local, parseable staging path."""


def _parse_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.name
    if suffix == ".py":
        units, edges = parse_python(text, rel)
        language = "python"
    elif suffix in {".r"}:
        units, edges = parse_r(text, rel)
        language = "r"
    elif suffix in {".rmd", ".qmd"}:
        units, edges = parse_rmd(text, rel)
        language = "rmd"
    else:
        raise AdapterUnavailable(f"unsupported code suffix: {suffix}")
    return {
        "file": rel,
        "language": language,
        "units": [asdict(unit) for unit in units],
        "edges": [asdict(edge) for edge in edges],
    }


class CodeLaneAdapter:
    def process(self, item: dict[str, Any]) -> str:
        path = Path(item.get("staged_path") or item.get("source_uri") or "")
        if not path.exists():
            raise AdapterUnavailable("staged code path not found")
        if path.is_file():
            files = [_parse_file(path)] if path.suffix.lower() in {".py", ".r", ".rmd", ".qmd"} else []
            if not files:
                raise AdapterUnavailable("zip/repo adapter pending; provide an extracted path")
        elif path.is_dir():
            files = []
            for candidate in sorted(path.rglob("*")):
                if candidate.suffix.lower() not in {".py", ".r", ".rmd", ".qmd"}:
                    continue
                if any(part in {".git", "__pycache__", "node_modules"} for part in candidate.parts):
                    continue
                files.append(_parse_file(candidate))
                if len(files) >= 200:
                    break
        else:
            raise AdapterUnavailable("staged code path not found")
        payload = {
            "source_kind": item.get("source_kind"),
            "files": files,
            "file_count": len(files),
            "unit_count": sum(len(file["units"]) for file in files),
        }
        session.set_item_parsed(item["import_id"], item["item_id"], payload)
        return "parsed"
