"""PG-backed protocol markdown export (G3.10e2)."""

from __future__ import annotations

from typing import Optional

from services.protocols import pg_read, pg_runs
from services.protocols.render import render_protocol_markdown


def export_markdown(protocol_id: str) -> Optional[str]:
    record = pg_read.get_protocol(protocol_id)
    if record is None:
        return None
    runs = pg_runs.list_runs(protocol_id, limit=200)
    return render_protocol_markdown(record, runs, protocol_id)
