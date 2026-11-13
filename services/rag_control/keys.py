"""R18: public key directory for seal verification."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import core_connection


def register(*, key_id: str, public_key: str, algorithm: str = "ed25519") -> None:
    pg = core_connection()
    try:
        pg.execute(
            """
            INSERT INTO rag_signing_keys (key_id,public_key,algorithm)
            VALUES (%s,%s,%s)
            ON CONFLICT (key_id) DO UPDATE SET
              public_key=EXCLUDED.public_key,
              algorithm=EXCLUDED.algorithm,
              last_seen_at=now()
            """,
            (key_id, public_key, algorithm),
        )
        pg.commit()
    finally:
        pg.close()


def list_keys() -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            "SELECT key_id,public_key,algorithm,first_seen_at,last_seen_at "
            "FROM rag_signing_keys ORDER BY first_seen_at DESC"
        ).fetchall()
        return [
            {
                "key_id": row["key_id"],
                "public_key": row["public_key"],
                "algorithm": row["algorithm"],
                "first_seen_at": row["first_seen_at"].isoformat() if row["first_seen_at"] else None,
                "last_seen_at": row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
            }
            for row in rows
        ]
    finally:
        pg.close()


def known(key_id: str, public_key: str) -> bool:
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT 1 FROM rag_signing_keys WHERE key_id=%s AND public_key=%s",
            (key_id, public_key),
        ).fetchone()
        return bool(row)
    finally:
        pg.close()
