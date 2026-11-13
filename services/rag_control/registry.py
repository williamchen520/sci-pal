"""RAG control plane: provider registry and health (R0)."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

import psycopg

from services.db.pg_pool import core_connection

MANIFEST_DIR = Path(__file__).with_name("manifests")


class RegistryError(ValueError):
    pass


def load_manifests() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(MANIFEST_DIR.glob("*.json"))
    ]


def manifest_hash(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row(row) -> dict[str, Any]:
    return {
        "rag_id": row["rag_id"],
        "version": row["version"],
        "display_name": row["display_name"],
        "capabilities": row["capabilities"] or [],
        "endpoint": row["endpoint"],
        "database_name": row["database_name"],
        "schema_version": row["schema_version"],
        "model_bindings": row["model_bindings"] or {},
        "resource_profile": row["resource_profile"] or {},
        "data_residency": row["data_residency"],
        "status": row["status"],
        "manifest_hash": row["manifest_hash"],
        "manifest": row["manifest"] or {},
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def seed() -> int:
    manifests = load_manifests()
    pg = core_connection()
    try:
        for manifest in manifests:
            rag_id = str(manifest.get("rag_id") or "").strip()
            if not rag_id:
                raise RegistryError("manifest missing rag_id")
            pg.execute(
                """
                INSERT INTO rag_providers
                  (rag_id, version, display_name, capabilities, endpoint, database_name,
                   schema_version, model_bindings, resource_profile, data_residency,
                   status, manifest_hash, manifest)
                VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb,%s,'unknown',%s,%s::jsonb)
                ON CONFLICT (rag_id) DO UPDATE SET
                  version=EXCLUDED.version,
                  display_name=EXCLUDED.display_name,
                  capabilities=EXCLUDED.capabilities,
                  endpoint=EXCLUDED.endpoint,
                  database_name=EXCLUDED.database_name,
                  schema_version=EXCLUDED.schema_version,
                  model_bindings=EXCLUDED.model_bindings,
                  resource_profile=EXCLUDED.resource_profile,
                  data_residency=EXCLUDED.data_residency,
                  manifest_hash=EXCLUDED.manifest_hash,
                  manifest=EXCLUDED.manifest,
                  updated_at=now()
                """,
                (
                    rag_id,
                    str(manifest.get("version") or "0.1.0"),
                    str(manifest.get("display_name") or rag_id),
                    json.dumps(manifest.get("capabilities") or []),
                    str(manifest.get("endpoint") or ""),
                    str(manifest.get("database_name") or ""),
                    int(manifest.get("schema_version") or 1),
                    json.dumps(manifest.get("model_bindings") or {}),
                    json.dumps(manifest.get("resource_profile") or {}),
                    str(manifest.get("data_residency") or "local"),
                    manifest_hash(manifest),
                    json.dumps(manifest, ensure_ascii=False),
                ),
            )
        pg.commit()
        return len(manifests)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def list_providers() -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute("SELECT * FROM rag_providers ORDER BY rag_id").fetchall()
        return [_row(row) for row in rows]
    finally:
        pg.close()


def get_provider(rag_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute("SELECT * FROM rag_providers WHERE rag_id=%s", (rag_id,)).fetchone()
        return _row(row) if row else None
    finally:
        pg.close()


def _check_http(health: dict[str, Any]) -> tuple[str, str]:
    url = os.environ.get(str(health.get("url_env") or ""), "").strip()
    url = url or str(health.get("default_url") or "")
    path = str(health.get("path") or "/health")
    try:
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        return ("active", "ok") if response.status == 200 and body.get("ok") else ("degraded", "not ok")
    except Exception as exc:  # noqa: BLE001
        return "offline", str(exc)


def _check_postgres(health: dict[str, Any]) -> tuple[str, str]:
    dsn = os.environ.get(str(health.get("dsn_env") or ""), "").strip()
    if not dsn:
        return "unknown", f"missing {health.get('dsn_env')}"
    query = str(health.get("query") or "SELECT 1")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            available = conn.execute(query).fetchone()[0]
        return ("active", "ok") if available else ("degraded", "query false")
    except Exception as exc:  # noqa: BLE001
        return "offline", str(exc)


def check_health(rag_id: str) -> dict[str, Any] | None:
    provider = get_provider(rag_id)
    if not provider:
        return None
    health = (provider["manifest"] or {}).get("health") or {}
    kind = health.get("type")
    started = time.perf_counter()
    if kind == "http":
        status, detail = _check_http(health)
    elif kind == "postgres":
        status, detail = _check_postgres(health)
    else:
        status, detail = "unknown", "no health check"
    latency = round((time.perf_counter() - started) * 1000, 2)
    pg = core_connection()
    try:
        pg.execute(
            "UPDATE rag_providers SET status=%s, updated_at=now() WHERE rag_id=%s",
            (status, rag_id),
        )
        pg.commit()
    finally:
        pg.close()
    return {
        "rag_id": rag_id,
        "status": status,
        "detail": detail,
        "latency_ms": latency,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
