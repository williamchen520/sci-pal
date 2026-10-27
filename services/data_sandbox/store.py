"""Editable data sandbox: projects, manifests, artifacts, validation, cloud gate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from services.data_sandbox import policy

DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent / "data_sandbox"


def root() -> Path:
    return Path(os.environ.get("SCIPAL_DATA_ROOT", str(DEFAULT_ROOT)))


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "default")
    return cleaned.strip("._") or "default"


def project_dir(owner: str, project_id: str) -> Path:
    return root() / _safe(owner) / _safe(project_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def create_project(
    owner: str,
    project_id: str,
    source_path: str,
    df: pd.DataFrame,
) -> Dict[str, Any]:
    directory = project_dir(owner, project_id)
    for sub in ("profile", "aggregates", "samples", "reports"):
        (directory / sub).mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    digest = hashlib.sha256(
        f"{source_path}:{len(df)}:{','.join(map(str, df.columns))}".encode()
    ).hexdigest()[:16]
    manifest = {
        "project_id": project_id,
        "owner": owner,
        "source": {
            "filename": Path(source_path).name,
            "filename_hash": f"sha256:{digest}",
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "ingested_at": _now(),
        },
        "policy": {
            "min_agg_n": policy.MIN_AGG_N,
            "cloud_eligible": False,
            "allowed_columns": [str(c) for c in df.columns if not policy.is_sensitive_column(str(c))],
            "redactions": [str(c) for c in df.columns if policy.is_sensitive_column(str(c))],
        },
        "artifacts": [],
    }
    _save_manifest(manifest_path, manifest)
    return manifest


def load_manifest(owner: str, project_id: str) -> Dict[str, Any]:
    return _load_manifest(project_dir(owner, project_id) / "manifest.json")


def _append_artifact(
    owner: str,
    project_id: str,
    kind: str,
    filename: str,
    rows: int,
    min_cell_n: int,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    manifest = load_manifest(owner, project_id)
    artifact = {
        "id": f"{kind}_{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "path": filename,
        "rows": rows,
        "min_cell_n": min_cell_n,
        "cloud_eligible": min_cell_n >= policy.MIN_AGG_N,
        "created_by": "data_profile",
        "created_at": _now(),
        **(extra or {}),
    }
    manifest.setdefault("artifacts", []).append(artifact)
    _save_manifest(project_dir(owner, project_id) / "manifest.json", manifest)
    return artifact


def write_profile(owner: str, project_id: str, df: pd.DataFrame) -> Dict[str, Any]:
    profile = policy.profile_frame(df)
    name = f"profile/{uuid.uuid4().hex[:8]}.json"
    target = project_dir(owner, project_id) / name
    target.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return _append_artifact(owner, project_id, "profile", name, profile["rows"], policy.MIN_AGG_N)


def write_aggregate(
    owner: str,
    project_id: str,
    frame: pd.DataFrame,
    group_by: List[str],
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    result = policy.aggregate_frame(frame, group_by, metrics)
    name = f"aggregates/{uuid.uuid4().hex[:8]}.csv"
    target = project_dir(owner, project_id) / name
    result.to_csv(target, index=False)
    min_cell = int(result["n"].min()) if "n" in result.columns and len(result) else 0
    return _append_artifact(owner, project_id, "aggregate", name, len(result), min_cell)


def write_sample(owner: str, project_id: str, df: pd.DataFrame) -> Dict[str, Any]:
    sample = policy.sample_frame(df)
    name = f"samples/{uuid.uuid4().hex[:8]}.csv"
    target = project_dir(owner, project_id) / name
    sample.to_csv(target, index=False)
    return _append_artifact(
        owner, project_id, "sample", name, len(sample), policy.MIN_AGG_N,
        {"rows_capped": policy.MAX_SAMPLE_ROWS},
    )


def _find(manifest: Dict[str, Any], artifact_id: str) -> Optional[Dict[str, Any]]:
    for artifact in manifest.get("artifacts") or []:
        if artifact.get("id") == artifact_id:
            return artifact
    return None


def list_artifacts(owner: str, project_id: str) -> List[Dict[str, Any]]:
    return load_manifest(owner, project_id).get("artifacts") or []


def read_artifact(owner: str, project_id: str, artifact_id: str) -> Dict[str, Any]:
    artifact = _find(load_manifest(owner, project_id), artifact_id)
    if not artifact:
        raise KeyError("artifact not found")
    path = project_dir(owner, project_id) / artifact["path"]
    return {"artifact": artifact, "content": path.read_text(encoding="utf-8")}


def update_artifact(
    owner: str, project_id: str, artifact_id: str, content: str
) -> Dict[str, Any]:
    manifest = load_manifest(owner, project_id)
    artifact = _find(manifest, artifact_id)
    if not artifact:
        raise KeyError("artifact not found")
    base = project_dir(owner, project_id) / artifact["path"]
    suffix = base.suffix
    new_name = f"{base.parent.name}/{uuid.uuid4().hex[:8]}{suffix}"
    target = project_dir(owner, project_id) / new_name
    target.write_text(content, encoding="utf-8")
    new_artifact = {
        **artifact,
        "id": f"{artifact['kind']}_{uuid.uuid4().hex[:8]}",
        "path": new_name,
        "created_at": _now(),
        "supersedes": artifact_id,
        "cloud_eligible": False,
    }
    manifest.setdefault("artifacts", []).append(new_artifact)
    _save_manifest(project_dir(owner, project_id) / "manifest.json", manifest)
    return new_artifact


def validate_artifact(owner: str, project_id: str, artifact_id: str) -> Dict[str, Any]:
    manifest = load_manifest(owner, project_id)
    artifact = _find(manifest, artifact_id)
    if not artifact:
        return {"ok": False, "reasons": ["artifact not found"]}
    path = project_dir(owner, project_id) / artifact["path"]
    reasons: List[str] = []
    if not path.exists():
        reasons.append("file missing")
    else:
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix == ".csv":
                frame = pd.read_csv(path)
                if "n" in frame.columns:
                    valid = frame["n"].dropna()
                    if (valid < policy.MIN_AGG_N).any():
                        reasons.append(f"cells below n={policy.MIN_AGG_N}")
                if artifact["kind"] == "sample":
                    if len(frame) > policy.MAX_SAMPLE_ROWS:
                        reasons.append("sample rows exceed cap")
                    if any(policy.is_sensitive_column(c) for c in frame.columns):
                        reasons.append("sensitive column in sample")
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"unreadable: {exc}")
    if artifact.get("min_cell_n", 0) < policy.MIN_AGG_N:
        reasons.append(f"min_cell_n < {policy.MIN_AGG_N}")
    ok = not reasons
    artifact["cloud_eligible"] = ok
    _save_manifest(project_dir(owner, project_id) / "manifest.json", manifest)
    return {"ok": ok, "reasons": reasons, "artifact": artifact}


def cloud_gate(owner: str, project_id: str, artifact_id: str) -> Dict[str, Any]:
    """Allow a derived artifact to go to the cloud only if it validates."""
    result = validate_artifact(owner, project_id, artifact_id)
    if not result["ok"]:
        return {"allow": False, "reasons": result["reasons"]}
    artifact = result["artifact"]
    if not artifact.get("cloud_eligible"):
        return {"allow": False, "reasons": ["cloud_eligible=false"]}
    return {
        "allow": True,
        "artifact_id": artifact_id,
        "kind": artifact["kind"],
        "min_cell_n": artifact.get("min_cell_n"),
    }
