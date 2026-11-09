"""PostgreSQL-backed protocol service facade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.protocols import (
    pg_attachments,
    pg_export,
    pg_import,
    pg_read,
    pg_runs,
)


class PGProtocolService:
    def __init__(self, db_path=None, client=None, storage_root=None) -> None:
        self.db_path = db_path
        self.client = client
        self.storage_root = storage_root

    def ensure_schema(self) -> None:
        return None

    def import_payload(self, payload, *, url: str = "") -> Dict[str, Any]:
        return pg_import.import_payload(payload, url=url)

    def import_protocol(self, protocol_id: str) -> Dict[str, Any]:
        return pg_import.import_protocol(protocol_id, self.client)

    def list(self, limit: int = 50, offset: int = 0, query: str = "") -> List[Dict[str, Any]]:
        return pg_read.list_protocols(limit, offset, query)

    def count(self, query: str = "") -> int:
        return pg_read.count_protocols(query)

    def get(self, protocol_id: str) -> Optional[Dict[str, Any]]:
        return pg_read.get_protocol(protocol_id)

    def add_run(self, protocol_id: str, **kwargs: Any) -> Dict[str, Any]:
        return pg_runs.add_run(protocol_id, **kwargs)

    def list_runs(self, protocol_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return pg_runs.list_runs(protocol_id, limit)

    def recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        return pg_runs.recent_runs(limit)

    def update_run(self, run_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        return pg_runs.update_run(run_id, **fields)

    def delete_run(self, run_id: str) -> bool:
        return pg_runs.delete_run(run_id)

    def add_attachment(self, run_id: str, filename: str, content_type: str, data: bytes) -> Dict:
        return pg_attachments.add_attachment(run_id, filename, content_type, data)

    def list_attachments(self, run_id: str) -> List[Dict]:
        return pg_attachments.list_attachments(run_id)

    def attachment_path(self, run_id: str, file_id: str):
        return pg_attachments.attachment_path(run_id, file_id)

    def delete_attachment(self, run_id: str, file_id: str) -> bool:
        return pg_attachments.delete_attachment(run_id, file_id)

    def export_markdown(self, protocol_id: str):
        return pg_export.export_markdown(protocol_id)
