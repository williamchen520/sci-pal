"""R2: model registry and index bindings."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from services.db.pg_pool import core_connection

MODELS_FILE = Path(__file__).with_name("models.json")


class ModelError(ValueError):
    pass


def _model(row) -> dict[str, Any]:
    return {
        "model_id": row["model_id"],
        "provider": row["provider"],
        "kind": row["kind"],
        "dimension": row["dimension"],
        "context_window": row["context_window"],
        "endpoint": row["endpoint"],
        "license": row["license"],
        "cost_profile": row["cost_profile"] or {},
        "status": row["status"],
        "metadata": row["metadata"] or {},
    }


def seed() -> int:
    models = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    pg = core_connection()
    try:
        for model in models:
            model_id = str(model.get("model_id") or "").strip()
            if not model_id:
                raise ModelError("model missing model_id")
            pg.execute(
                """
                INSERT INTO rag_models
                  (model_id,provider,kind,dimension,context_window,endpoint,license,cost_profile,status,metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'active',%s::jsonb)
                ON CONFLICT (model_id) DO UPDATE SET
                  provider=EXCLUDED.provider,
                  kind=EXCLUDED.kind,
                  dimension=EXCLUDED.dimension,
                  context_window=EXCLUDED.context_window,
                  endpoint=EXCLUDED.endpoint,
                  license=EXCLUDED.license,
                  cost_profile=EXCLUDED.cost_profile,
                  metadata=EXCLUDED.metadata,
                  updated_at=now()
                """,
                (
                    model_id,
                    str(model.get("provider") or "local"),
                    str(model.get("kind") or "embedding"),
                    model.get("dimension"),
                    model.get("context_window"),
                    str(model.get("endpoint") or ""),
                    str(model.get("license") or ""),
                    json.dumps(model.get("cost_profile") or {}),
                    json.dumps(model.get("metadata") or {}),
                ),
            )
        pg.commit()
        return len(models)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def list_models() -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        return [_model(row) for row in pg.execute("SELECT * FROM rag_models ORDER BY model_id").fetchall()]
    finally:
        pg.close()


def get_model(model_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute("SELECT * FROM rag_models WHERE model_id=%s", (model_id,)).fetchone()
        return _model(row) if row else None
    finally:
        pg.close()


def _binding(row) -> dict[str, Any]:
    return {
        "binding_id": row["binding_id"],
        "rag_id": row["rag_id"],
        "library_id": row["library_id"],
        "index_name": row["index_name"],
        "embedding_model": row["embedding_model"],
        "dimension": row["dimension"],
        "schema_version": row["schema_version"],
        "snapshot": row["snapshot"],
        "status": row["status"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def list_bindings(*, rag_id: str = "", library_id: str = "") -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM rag_index_bindings WHERE (%s='' OR rag_id=%s) AND (%s='' OR library_id=%s) "
            "ORDER BY rag_id,library_id,index_name",
            (rag_id, rag_id, library_id, library_id),
        ).fetchall()
        return [_binding(row) for row in rows]
    finally:
        pg.close()


def register_binding(
    *,
    rag_id: str,
    library_id: str,
    index_name: str,
    embedding_model: str,
    dimension: int | None = None,
    schema_version: int = 1,
    snapshot: str = "",
    status: str = "active",
) -> dict[str, Any]:
    if not rag_id or not library_id or not index_name:
        raise ModelError("rag_id, library_id, index_name are required")
    model = get_model(embedding_model)
    if not model or model["kind"] != "embedding":
        raise ModelError("embedding model not registered")
    expected = model["dimension"]
    if expected is not None and dimension is not None and int(dimension) != int(expected):
        raise ModelError("dimension does not match model")
    dimension = int(expected if dimension is None else dimension)
    pg = core_connection()
    try:
        existing = pg.execute(
            "SELECT * FROM rag_index_bindings WHERE rag_id=%s AND library_id=%s AND index_name=%s",
            (rag_id, library_id, index_name),
        ).fetchone()
        if existing and (existing["embedding_model"] != embedding_model or existing["dimension"] != dimension):
            raise ModelError("model change requires a new index; reindex instead")
        binding_id = existing["binding_id"] if existing else "bind_" + uuid.uuid4().hex[:12]
        pg.execute(
            """
            INSERT INTO rag_index_bindings
              (binding_id,rag_id,library_id,index_name,embedding_model,dimension,schema_version,snapshot,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (rag_id,library_id,index_name) DO UPDATE SET
              snapshot=EXCLUDED.snapshot,
              schema_version=EXCLUDED.schema_version,
              status=EXCLUDED.status,
              updated_at=now()
            """,
            (
                binding_id,
                rag_id,
                library_id,
                index_name,
                embedding_model,
                dimension,
                int(schema_version),
                snapshot,
                status,
            ),
        )
        pg.commit()
        row = pg.execute("SELECT * FROM rag_index_bindings WHERE binding_id=%s", (binding_id,)).fetchone()
        return _binding(row)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
