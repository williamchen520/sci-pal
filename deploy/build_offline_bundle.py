"""Build an offline SciPal bundle.

The bundle contains source, deploy files, install script and a manifest. With
``--images`` it can also carry `docker save` archives for air-gapped installs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git",
    ".github",
    ".githooks",
    ".vscode",
    "venv_sciPal_py312",
    "data",
    "documents",
    "documents_xml",
    "models",
    "logs",
    "backups",
    "__pycache__",
    ".pytest_cache",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".db", ".sqlite", ".sqlite3"}
KEEP_ENV = {".env.example"}


def _ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        path = Path(directory) / name
        if name in SKIP_DIRS:
            ignored.add(name)
        elif path.suffix in SKIP_SUFFIXES:
            ignored.add(name)
        elif name.startswith(".env") and name not in KEEP_ENV:
            ignored.add(name)
    return ignored


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "backups"))
    parser.add_argument(
        "--images",
        default="",
        help="comma-separated docker image refs to docker save into images/",
    )
    parser.add_argument("--name", default="scipal-offline")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = out / f"{args.name}-{stamp}.tar.gz"

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        stage = Path(tmp)
        app_dir = stage / "app"
        shutil.copytree(ROOT, app_dir, ignore=_ignore, dirs_exist_ok=True)
        images = [item.strip() for item in args.images.split(",") if item.strip()]
        if images:
            image_dir = stage / "images"
            image_dir.mkdir()
            for image in images:
                target = image_dir / f"{image.replace('/', '_').replace(':', '_')}.tar"
                subprocess.run(["docker", "save", "-o", str(target), image], check=True)
        install = stage / "install.sh"
        install.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -d images ]; then
  for image in images/*.tar; do
    [ -e "$image" ] || continue
    echo "loading $image"
    docker load -i "$image"
  done
fi
cd app
if [ ! -f deploy/.env ]; then
  cp deploy/.env.example deploy/.env
  echo "Created deploy/.env; edit secrets and model endpoints before production use."
fi
docker compose -f deploy/docker-compose.yml up -d --build
echo "SciPal started. Open http://<host>/login.html"
""",
            encoding="utf-8",
        )
        install.chmod(0o755)
        items = []
        for path in sorted(stage.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                items.append(
                    {
                        "path": str(path.relative_to(stage)).replace("\\", "/"),
                        "size": path.stat().st_size,
                        "sha256": _sha256(path),
                    }
                )
        manifest = {
            "name": args.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip()
            if (ROOT / "VERSION").exists()
            else "",
            "images": images,
            "items": items,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with tarfile.open(archive, "w:gz") as tar:
            for path in sorted(stage.iterdir()):
                tar.add(path, arcname=path.name)
    print(archive)
    print(f"files={len(manifest['items'])} size_mb={archive.stat().st_size / 1024 / 1024:.1f}")


if __name__ == "__main__":
    main()
