#!/usr/bin/env python3
"""Parse an OA article HTML file into structured JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.papers.html_parser import parse_html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html_file")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    data = parse_html(Path(args.html_file).read_bytes(), source_url=args.source_url)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    print(
        f"HTML_PARSE_OK title={len(data['title'])} sections={len(data['sections'])} "
        f"figures={len(data['figures'])} code_links={len(data['code_links'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
