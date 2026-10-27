"""MinerU 4.x parser adapter.

MinerU 4 moved from the old ``magic_pdf`` Python API to a CLI + local parse
server (``mineru-api`` on :8000). This adapter shells out to the CLI with
``--json`` and converts the returned Markdown into our paragraph schema.

Requirements (checked lazily):

* ``mineru-api --tier basic --port 8000`` running in the background;
* ``mineru config set parse_server.local.mode self_hosted`` and
  ``... self_hosted_url http://127.0.0.1:8000``;
* basic-tier models downloaded with ``mineru-models-download --tier basic``.

When any of that is missing the parser falls back to a stub; the pipeline's
quality gate keeps the stub from replacing a good Docling result.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .base_parser import BaseParser

_PAGE_MARKER = re.compile(r"<!--\s*page\s+(\d+)\s+of\s+(\d+)\s*-->")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _section_type(title: str) -> str:
    lower = (title or "").lower()
    if any(k in lower for k in ("abstract", "summary")):
        return "abstract"
    if any(k in lower for k in ("introduction", "background")):
        return "introduction"
    if any(k in lower for k in ("method", "material", "experiment")):
        return "methods"
    if any(k in lower for k in ("result", "finding")):
        return "results"
    if any(k in lower for k in ("discussion", "conclusion")):
        return "discussion"
    if any(k in lower for k in ("reference", "bibliography")):
        return "references"
    return "body"


class MinerUParser(BaseParser):
    """MinerU 4.x CLI adapter (markdown -> paragraphs)."""

    def __init__(
        self,
        output_dir: str | None = None,
        cli_path: str | None = None,
        api_url: str = "http://127.0.0.1:8000",
        wait_seconds: int = 900,
    ) -> None:
        self.name = "mineru"
        self.output_dir = output_dir or str(Path("data") / "parsed_output")
        self.api_url = api_url
        self.wait_seconds = wait_seconds
        self.cli_path = cli_path or self._find_cli()
        self._available: bool | None = None

    # ------------------------------------------------------------------
    @staticmethod
    def _find_cli() -> str:
        scripts = Path(sys.executable).parent
        candidate = scripts / ("mineru.exe" if os.name == "nt" else "mineru")
        return str(candidate)

    def get_parser_name(self) -> str:
        return self.name

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        if not Path(self.cli_path).exists():
            self._available = False
            return False
        try:
            import urllib.request

            for path in ("/openapi.json", "/health", "/healthz"):
                try:
                    with urllib.request.urlopen(f"{self.api_url}{path}", timeout=3) as response:
                        if response.status == 200:
                            self._available = True
                            return True
                except Exception:  # noqa: BLE001
                    continue
            self._available = False
        except Exception:  # noqa: BLE001
            self._available = False
        return bool(self._available)

    # ------------------------------------------------------------------
    def parse(self, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        if not self.is_available():
            print("⚠️  MinerU parse-server not available (mineru-api on 8000); using stub")
            return self._stub_parse(pdf_path, paper_id)

        with tempfile.TemporaryDirectory(prefix="mineru_out_") as tmp:
            out_path = Path(tmp) / "out"
            command = [
                self.cli_path,
                "parse",
                str(pdf_path),
                "--pages",
                "all",
                "--wait",
                str(self.wait_seconds),
                "--json",
                "-o",
                str(out_path),
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.wait_seconds + 60,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️  MinerU CLI failed: {str(exc)[:120]}; using stub")
                return self._stub_parse(pdf_path, paper_id)

            payload = self._parse_cli_json(completed.stdout)
            if payload.get("error"):
                print(f"⚠️  MinerU error: {payload['error'].get('message', '')[:120]}; using stub")
                return self._stub_parse(pdf_path, paper_id)

            markdown = self._read_output(out_path)
            if not markdown:
                print("⚠️  MinerU produced no markdown; using stub")
                return self._stub_parse(pdf_path, paper_id)

        paragraphs, figures, title = self._markdown_to_result(markdown, paper_id)
        return {
            "paper_id": paper_id,
            "paragraphs": paragraphs,
            "figures": figures,
            "tables": [],
            "citations": [],
            "metadata": {
                "paper_id": paper_id,
                "file_path": str(pdf_path),
                "file_name": os.path.basename(pdf_path),
                "title": title or Path(pdf_path).stem,
                "parse_engine": "mineru",
                "parse_status": "completed",
            },
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_cli_json(stdout: str) -> Dict[str, Any]:
        text = (stdout or "").strip()
        if not text:
            return {}
        start = text.find("{")
        if start < 0:
            return {}
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _read_output(out_path: Path) -> str:
        if out_path.is_file():
            return out_path.read_text(encoding="utf-8", errors="replace")
        if out_path.is_dir():
            for candidate in sorted(out_path.rglob("*")):
                if candidate.is_file():
                    return candidate.read_text(encoding="utf-8", errors="replace")
        return ""

    def _markdown_to_result(
        self, markdown: str, paper_id: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        paragraphs: List[Dict[str, Any]] = []
        figures: List[Dict[str, Any]] = []
        page = 1
        section_title = ""
        section_type = "body"
        title = ""
        buffer: List[str] = []
        index = 0

        def flush() -> None:
            nonlocal buffer, index
            text = "\n".join(line for line in buffer if line.strip()).strip()
            buffer = []
            if not text:
                return
            index += 1
            paragraphs.append(
                {
                    "para_id": f"{paper_id}_p{index:03d}",
                    "paper_id": paper_id,
                    "page_number": page,
                    "section_type": section_type,
                    "section_title": section_title,
                    "section_name": section_title or "Body",
                    "para_index": index,
                    "text_content": text,
                    "parser_source": "mineru",
                }
            )

        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            page_match = _PAGE_MARKER.search(line)
            if page_match:
                flush()
                page = int(page_match.group(1))
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
            if heading_match:
                flush()
                heading = heading_match.group(2).strip()
                if not title and len(heading_match.group(1)) == 1:
                    title = heading
                section_title = heading
                section_type = _section_type(heading)
                continue

            image_match = _IMAGE.search(line)
            if image_match and not line.replace(image_match.group(0), "").strip():
                figures.append(
                    {
                        "figure_id": f"{paper_id}_fig{len(figures) + 1:03d}",
                        "paper_id": paper_id,
                        "page_number": page,
                        "figure_type": "figure",
                        "caption": image_match.group(1) or "",
                        "image_path": image_match.group(2),
                        "parser_source": "mineru",
                    }
                )
                continue

            if not line.strip():
                flush()
                continue
            buffer.append(line)

        flush()
        return paragraphs, figures, title

    # ------------------------------------------------------------------
    def _stub_parse(self, pdf_path: str, paper_id: str) -> Dict[str, Any]:
        return {
            "paper_id": paper_id,
            "paragraphs": [
                {
                    "para_id": f"{paper_id}_p001",
                    "paper_id": paper_id,
                    "page_number": 1,
                    "section_type": "body",
                    "section_title": "",
                    "para_index": 1,
                    "text_content": f"[MinerU stub] {Path(pdf_path).stem}",
                    "parser_source": "mineru-stub",
                }
            ],
            "figures": [],
            "tables": [],
            "citations": [],
            "metadata": {
                "paper_id": paper_id,
                "file_path": str(pdf_path),
                "file_name": os.path.basename(pdf_path),
                "title": Path(pdf_path).stem,
                "parse_engine": "mineru-stub",
                "parse_status": "stub",
            },
        }
