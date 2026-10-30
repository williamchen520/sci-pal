"""Declarative domain pack loader.

A pack is a directory with a ``pack.yaml`` manifest plus optional taxonomy,
section types, evidence schema, sources and prompts. Core code only depends on
this loader; domain vocabulary lives in ``packs/``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PACK_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{1,80}$")
REQUIRED_MANIFEST = ("id", "version", "discipline", "license")
DEFAULT_PACKS_DIR = PROJECT_ROOT / "packs"


class PackError(ValueError):
    """Raised when a pack cannot be loaded."""


@dataclass
class DomainPack:
    path: Path
    manifest: Dict[str, Any]
    taxonomy: Dict[str, Any] = field(default_factory=dict)
    section_types: Dict[str, Any] = field(default_factory=dict)
    evidence_schema: Dict[str, Any] = field(default_factory=dict)
    sources: Dict[str, Any] = field(default_factory=dict)
    prompts: Dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.manifest.get("id") or self.path.name)

    @property
    def version(self) -> str:
        return str(self.manifest.get("version") or "0.0.0")

    @property
    def name(self) -> str:
        return str(self.manifest.get("name") or self.id)

    def summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "discipline": self.manifest.get("discipline"),
            "language": self.manifest.get("language"),
            "license": self.manifest.get("license"),
            "description": self.manifest.get("description"),
            "extends": self.manifest.get("extends"),
            "path": str(self.path),
            "term_count": len(self.taxonomy.get("terms") or []),
            "section_types": list((self.section_types.get("types") or {}).keys()),
            "prompts": sorted(self.prompts),
        }


def packs_dir() -> Path:
    return Path(os.environ.get("SCIPAL_PACKS_DIR") or DEFAULT_PACKS_DIR)


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise PackError(f"missing file: {path.name}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(f"invalid yaml: {path.name}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PackError(f"expected mapping: {path.name}")
    return data


def _safe_child(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise PackError(f"path escapes pack: {value}")
    return path


def load_pack(path: Path | str) -> DomainPack:
    root = Path(path).resolve()
    manifest = _read_yaml(root / "pack.yaml")
    missing = [key for key in REQUIRED_MANIFEST if not manifest.get(key)]
    if missing:
        raise PackError(f"missing manifest fields: {', '.join(missing)}")
    if not PACK_ID_RE.match(str(manifest["id"])):
        raise PackError(f"invalid pack id: {manifest['id']}")
    pack = DomainPack(path=root, manifest=manifest)
    files = {
        "taxonomy": manifest.get("taxonomy", "taxonomy.yaml"),
        "section_types": manifest.get("section_types", "section_types.yaml"),
        "evidence_schema": manifest.get("evidence_schema", "evidence_schema.yaml"),
        "sources": manifest.get("sources", "sources.yaml"),
    }
    for attr, relative in files.items():
        candidate = _safe_child(root, str(relative))
        if candidate.exists():
            setattr(pack, attr, _read_yaml(candidate))
    prompt_map = manifest.get("prompts") or {}
    if isinstance(prompt_map, dict):
        for name, relative in prompt_map.items():
            candidate = _safe_child(root, str(relative))
            if candidate.exists():
                pack.prompts[str(name)] = candidate.read_text(encoding="utf-8")
    return pack


def _iter_pack_dirs() -> Iterable[Path]:
    root = packs_dir()
    if not root.exists():
        return []
    return sorted(
        path for path in root.iterdir() if path.is_dir() and (path / "pack.yaml").exists()
    )


def list_packs() -> List[DomainPack]:
    packs = []
    for path in _iter_pack_dirs():
        try:
            packs.append(load_pack(path))
        except PackError:
            continue
    return packs


def get_pack(pack_id: str) -> Optional[DomainPack]:
    for pack in list_packs():
        if pack.id == pack_id:
            return pack
    return None


def validate_pack(path: Path | str) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    try:
        pack = load_pack(path)
    except PackError as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": []}

    terms = pack.taxonomy.get("terms") or []
    if not isinstance(terms, list) or not terms:
        warnings.append("taxonomy.terms is empty")
    seen_terms = set()
    for index, term in enumerate(terms if isinstance(terms, list) else []):
        if not isinstance(term, dict):
            errors.append(f"taxonomy.terms[{index}] must be a mapping")
            continue
        term_id = str(term.get("id") or "").strip()
        if not term_id:
            errors.append(f"taxonomy.terms[{index}].id is required")
        elif term_id in seen_terms:
            errors.append(f"duplicate term id: {term_id}")
        seen_terms.add(term_id)
        if not term.get("label"):
            warnings.append(f"term {term_id or index} has no label")

    types = pack.section_types.get("types") or {}
    if not isinstance(types, dict) or not types:
        warnings.append("section_types.types is empty")
    for name, config in (types.items() if isinstance(types, dict) else []):
        if not isinstance(config, dict):
            errors.append(f"section type {name} must be a mapping")

    schema = pack.evidence_schema or {}
    fields = schema.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        errors.append("evidence_schema.fields is required")
    required = schema.get("required") or []
    for name in required if isinstance(required, list) else []:
        if name not in (fields or {}):
            errors.append(f"required evidence field not defined: {name}")

    if not pack.prompts:
        warnings.append("no prompts declared")
    for name, text in pack.prompts.items():
        if len(text.strip()) < 20:
            warnings.append(f"prompt {name} is very short")

    return {
        "ok": not errors,
        "pack_id": pack.id,
        "version": pack.version,
        "errors": errors,
        "warnings": warnings,
        "summary": pack.summary(),
    }
