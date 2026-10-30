"""CLI for domain packs: list, info, validate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.domain_packs import get_pack, list_packs, load_pack, validate_pack


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    info = sub.add_parser("info")
    info.add_argument("pack")
    validate = sub.add_parser("validate")
    validate.add_argument("path")
    args = parser.parse_args()

    if args.command == "list":
        for pack in list_packs():
            print(f"{pack.id}\t{pack.version}\t{pack.name}\t{pack.path}")
        return 0
    if args.command == "info":
        pack = get_pack(args.pack)
        if not pack:
            print(f"pack not found: {args.pack}", file=sys.stderr)
            return 1
        print(pack.summary())
        return 0
    result = validate_pack(args.path)
    print(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
