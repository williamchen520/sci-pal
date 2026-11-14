"""U0: safe multipart upload staging for imports."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from services.imports import session

ALLOWED_EXTENSIONS = {".html", ".htm", ".pdf", ".xml"}
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_FILES = 50
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadError(ValueError):
    """Invalid or unsafe upload."""


def staging_root() -> Path:
    raw = os.environ.get("SCIPAL_IMPORT_STAGING_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "data" / "imports" / "staging").resolve()


def _safe_name(name: str) -> str:
    base = Path(name or "").name
    cleaned = SAFE_NAME.sub("_", base).strip("._")
    if not cleaned:
        raise UploadError("empty filename")
    if Path(cleaned).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UploadError(f"unsupported extension: {cleaned}")
    return cleaned


def save_uploaded_files(
    files: list[Any],
    *,
    tenant_id: str,
    library_id: str,
    origin: str = "dsh",
    created_by: str = "",
) -> dict[str, Any]:
    if not library_id:
        raise UploadError("library_id is required")
    if not files:
        raise UploadError("no files")
    if len(files) > MAX_FILES:
        raise UploadError(f"too many files (max {MAX_FILES})")

    batch_dir = staging_root() / uuid.uuid4().hex[:16]
    batch_dir.mkdir(parents=True, exist_ok=False)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        for uploaded in files:
            name = _safe_name(getattr(uploaded, "filename", ""))
            if name in seen:
                stem, suffix = Path(name).stem, Path(name).suffix
                index = 2
                while f"{stem}_{index}{suffix}" in seen:
                    index += 1
                name = f"{stem}_{index}{suffix}"
            seen.add(name)
            data = uploaded.read()
            if len(data) > MAX_FILE_BYTES:
                raise UploadError(f"file too large: {name}")
            path = batch_dir / name
            path.write_bytes(data)
            items.append(
                {
                    "uri": name,
                    "staged_path": str(path),
                    "content_hash": hashlib.sha256(data).hexdigest(),
                }
            )
        return session.create_import(
            tenant_id=tenant_id,
            library_id=library_id,
            origin="dsh" if origin not in {"manual", "api"} else origin,
            items=items,
            created_by=created_by,
        )
    except Exception:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise
