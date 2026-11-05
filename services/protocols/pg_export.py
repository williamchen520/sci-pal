"""PG-backed protocol markdown export (G3.10e2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.protocols import pg_read, pg_runs
from services.protocols.service import ProtocolService


class _Renderer(ProtocolService):
    def __init__(self, record: Dict[str, Any], runs: List[Dict[str, Any]]):
        super().__init__("/tmp/scipal-protocol-render.db")
        self._record = record
        self._runs = runs

    def get(self, protocol_id: str):
        return self._record

    def list_runs(self, protocol_id: str, limit: int = 50):
        return self._runs


def export_markdown(protocol_id: str) -> Optional[str]:
    record = pg_read.get_protocol(protocol_id)
    if record is None:
        return None
    runs = pg_runs.list_runs(protocol_id, limit=200)
    return _Renderer(record, runs).export_markdown(protocol_id)
