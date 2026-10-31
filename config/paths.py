"""Canonical project paths.

All runtime paths are derived from this file or environment variables; no code
should hardcode a Windows drive or a Linux absolute path.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


DATA_DIR = _env_path("SCIPAL_DATA_DIR", PROJECT_ROOT / "data")
DOCUMENTS_DIR = _env_path("SCIPAL_DOCUMENTS_DIR", PROJECT_ROOT / "documents")
XML_DIR = _env_path("SCIPAL_XML_DIR", PROJECT_ROOT / "documents_xml")
LOGS_DIR = _env_path("SCIPAL_LOGS_DIR", PROJECT_ROOT / "logs")
MODELS_DIR = _env_path("SCIPAL_MODELS_DIR", PROJECT_ROOT / "models")

DB_PATH = _env_path("SCIPAL_DB_PATH", DATA_DIR / "research.db")
CHROMA_PATH = _env_path("SCIPAL_CHROMA_PATH", DATA_DIR / "chroma")


def _model(env_name: str, default_id: str, local_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    local = MODELS_DIR / local_name
    if local.exists():
        return str(local)
    return default_id


# Hugging Face IDs are portable defaults; set SCIPAL_EMBEDDING_MODEL /
# SCIPAL_RERANK_MODEL to a local directory for offline deployments.
EMBEDDING_MODEL = _model(
    "SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5", "bge-base-en-v1.5"
)
RERANK_MODEL = _model(
    "SCIPAL_RERANK_MODEL", "BAAI/bge-reranker-base", "bge-reranker-base"
)
