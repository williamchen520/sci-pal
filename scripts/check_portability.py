#!/usr/bin/env python3
"""Scan Python code for Windows-only or cwd-dependent paths.

Exit code 0 means clean; 1 means findings. Intended as a pre-commit/CI guard.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WINDOWS_DRIVE = re.compile(r"\b[A-Za-z]:[\\/]")
POSIX_ABS = re.compile(r"(?<![\w:])/(?:home|data/models|opt|mnt|usr|var)/")
VENV_PYTHON = re.compile(r"venv[^\s\"']*[/\\](?:Scripts[/\\]python|bin[/\\]python)")
CWD_DEPENDENCY = re.compile(r"os\.getcwd\(\)|Path\.cwd\(\)")
TMP_LITERAL = re.compile(r"[\"']/tmp/")

SKIP_DIRS = {
    ".git",
    "venv",
    "venv_sciPal_py312",
    "node_modules",
    "__pycache__",
    "data",
    "documents",
    "documents_xml",
    "backups",
    "tests",
}


def issues_in(path: Path) -> list[str]:
    findings = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"cannot read: {exc}"]
    for lineno, line in enumerate(lines, 1):
        if "http://" in line or "https://" in line:
            continue
        if line.lstrip().startswith("#!") or "#!/usr/bin/env" in line:
            continue
        checks = (
            ("windows-drive", WINDOWS_DRIVE),
            ("posix-absolute", POSIX_ABS),
            ("venv-python", VENV_PYTHON),
            ("cwd-dependent", CWD_DEPENDENCY),
            ("tmp-literal", TMP_LITERAL),
        )
        for label, pattern in checks:
            if label == "cwd-dependent" and path.name == "self_check.py":
                continue
            if pattern.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{lineno}: {label}: {line.strip()[:180]}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        findings.extend(issues_in(path))
    if findings:
        print("\n".join(findings))
        print(f"\n{len(findings)} portability issue(s)")
        return 1
    print("portability check: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
