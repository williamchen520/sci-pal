"""Code-lane parsing adapter (staging JSON only, never executes code)."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from code_rag.parsers import parse_python, parse_r, parse_rmd
from services.imports import session
from services.imports.code_build import build_code


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
    def __init__(self, *, build: bool = False) -> None:
        self.build = build

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
        if self.build:
            build = build_code(item, payload)
            payload["build"] = build
            payload["index"] = _index_code(item, build)
        session.set_item_parsed(item["import_id"], item["item_id"], payload)
        return "built" if self.build else "parsed"


def _index_code(item: dict[str, Any], build: dict[str, Any]) -> dict[str, Any]:
    dsn = os.environ.get("SCIPAL_CODE_DSN", "").strip()
    if not dsn or os.environ.get("SCIPAL_CODE_INDEX", "1") == "0":
        return {"status": "skipped", "reason": "no dsn or disabled"}
    try:
        from code_rag.index import index_library

        result = index_library(
            dsn,
            str(item.get("library_id") or "lib_default"),
            str(build.get("snapshot_id") or ""),
            model_name=os.environ.get("SCIPAL_CODE_EMBED_MODEL", ""),
            device=os.environ.get("SCIPAL_CODE_DEVICE", ""),
        )
        return {"status": "indexed", **result}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:300]}
