"""Guard against unsafe destructive SQL.  # sql_guard: allow-file

Rules:
  1. DROP TABLE / TRUNCATE / ALTER TABLE targets must be schema-qualified.
  2. DROP TABLE / TRUNCATE may name only one table.
  3. DROP TABLE / TRUNCATE require explicit --allow-destructive.
  4. DROP DATABASE / DROP SCHEMA always require --allow-destructive.
  5. A line or file can opt out with ``# sql_guard: allow``.

This is intentionally conservative and stdlib-only so it can run in CI and in
the pre-commit hook without the project venv.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

IDENT = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
QUALIFIED = rf"{IDENT}\s*\.\s*{IDENT}"
TABLE_HEAD = re.compile(r"(?is)\b(DROP\s+TABLE|TRUNCATE(?:\s+TABLE)?|ALTER\s+TABLE)\b")
DROP_SCHEMA = re.compile(r"(?is)\bDROP\s+(?:SCHEMA|DATABASE)\b")
QUALIFIED_RE = re.compile(rf"^{QUALIFIED}$")
IDENT_RE = re.compile(rf"^{IDENT}$")
ALLOW_LINE = re.compile(r"#\s*sql_guard:\s*allow\b")
ALLOW_FILE = re.compile(r"#\s*sql_guard:\s*allow-file\b")


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    sql: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.sql}"


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _target_part(statement: str) -> str:
    body = TABLE_HEAD.sub("", statement, count=1).strip()
    body = re.sub(r"(?is)^IF\s+EXISTS\s+", "", body)
    body = re.sub(r"(?is)^ONLY\s+", "", body)
    body = re.sub(r"(?is)^CONCURRENTLY\s+", "", body)
    body = re.split(
        r"(?is)\b(?:CASCADE|RESTRICT|ADD|DROP|ALTER|RENAME|SET|OWNER|ATTACH|DETACH|WITH|TABLESPACE)\b",
        body,
        maxsplit=1,
    )[0]
    return body.strip().rstrip(";").strip()


def _split_targets(body: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    quote = ""
    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in ('"', "'"):
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def analyze_text(
    text: str,
    *,
    path: str = "<text>",
    allow_destructive: bool = False,
    forbid_schema: str | None = None,
) -> List[Finding]:
    findings: List[Finding] = []
    if ALLOW_FILE.search(text):
        return findings

    for match in DROP_SCHEMA.finditer(text):
        line = _line_of(text, match.start())
        if ALLOW_LINE.search(text.splitlines()[line - 1]):
            continue
        if not allow_destructive:
            findings.append(Finding(path, line, "DROP SCHEMA/DATABASE requires --allow-destructive", match.group(0)))
        continue

    for match in TABLE_HEAD.finditer(text):
        start = match.start()
        line = _line_of(text, start)
        src_lines = text.splitlines()
        if line <= len(src_lines) and (
            ALLOW_LINE.search(src_lines[line - 1])
            or (line > 1 and ALLOW_LINE.search(src_lines[line - 2]))
        ):
            continue
        statement = text[start : text.find(";", start) if ";" in text[start:] else len(text)]
        statement = statement.split("\n\n", 1)[0].strip()
        keyword = re.sub(r"\s+", " ", match.group(1)).upper()
        body = _target_part(statement)
        if not body:
            continue
        targets = _split_targets(body)
        destructive = keyword.startswith(("DROP", "TRUNCATE"))
        if destructive and not allow_destructive:
            findings.append(Finding(path, line, f"{keyword} requires --allow-destructive", statement[:120]))
        if len(targets) > 1:
            findings.append(Finding(path, line, f"{keyword} may name only one table", statement[:120]))
        for target in targets:
            normalized = re.sub(r"\s+", "", target)
            if not QUALIFIED_RE.match(normalized):
                findings.append(Finding(path, line, f"{keyword} target is not schema-qualified", target))
                continue
            schema = normalized.split(".", 1)[0].strip('"')
            if forbid_schema and schema.lower() == forbid_schema.lower():
                findings.append(Finding(path, line, f"{keyword} target schema {schema!r} is forbidden", target))
    return findings


def scan_paths(
    paths: Iterable[Path],
    *,
    allow_destructive: bool = False,
    forbid_schema: str | None = None,
) -> List[Finding]:
    findings: List[Finding] = []
    for path in paths:
        if path.suffix.lower() not in {".py", ".sql"} or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings.extend(
            analyze_text(
                text,
                path=str(path),
                allow_destructive=allow_destructive,
                forbid_schema=forbid_schema,
            )
        )
    return findings


def _git_changed(staged: bool) -> List[Path]:
    if staged:
        command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    else:
        base = os.environ.get("GITHUB_BASE_REF", "").strip()
        if base:
            command = ["git", "diff", "--name-only", "--diff-filter=ACMR", f"origin/{base}...HEAD"]
        else:
            command = ["git", "diff", "--name-only", "HEAD", "--diff-filter=ACMR"]
    output = subprocess.check_output(command, text=True)
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files or directories to scan")
    parser.add_argument("--staged", action="store_true", help="scan staged git files")
    parser.add_argument("--changed", action="store_true", help="scan changed files vs HEAD or PR base")
    parser.add_argument("--allow-destructive", action="store_true", help="allow DROP/TRUNCATE")
    parser.add_argument("--forbid-schema", default="", help="reject targets in this schema, e.g. public")
    args = parser.parse_args(argv)

    paths: List[Path] = []
    if args.staged or args.changed:
        paths.extend(_git_changed(staged=args.staged))
    for item in args.paths:
        path = Path(item)
        if path.is_dir():
            paths.extend(path.rglob("*.py"))
            paths.extend(path.rglob("*.sql"))
        else:
            paths.append(path)
    findings = scan_paths(
        paths,
        allow_destructive=args.allow_destructive,
        forbid_schema=args.forbid_schema or None,
    )
    for finding in findings:
        print(finding)
    if findings:
        print(f"sql_guard: {len(findings)} unsafe SQL finding(s)", file=sys.stderr)
        return 1
    print("sql_guard: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
