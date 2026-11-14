"""N0 orchestrator: route items and invoke lane adapters."""

from __future__ import annotations

from typing import Any, Protocol

from services.imports import session
from services.imports.router import route


class SlotAdapter(Protocol):
    def process(self, item: dict[str, Any]) -> str: ...


def process_import(
    import_id: str,
    *,
    paper_adapter: SlotAdapter | None = None,
    code_adapter: SlotAdapter | None = None,
) -> dict[str, Any]:
    payload = session.get_import(import_id)
    processed = 0
    failed = 0
    for item in payload["items"]:
        status = item["status"]
        if status in {"draft", "indexed", "failed", "quarantined"}:
            continue
        routed = route(item["source_kind"])
        if routed.lane == "quarantine":
            session.set_item_status(import_id, item["item_id"], "quarantined", routed.reason)
            continue
        session.set_item_status(import_id, item["item_id"], "routed")
        adapter = paper_adapter if routed.lane == "paper" else code_adapter
        if adapter is None:
            session.set_item_status(
                import_id,
                item["item_id"],
                "routed",
                f"adapter not configured for {routed.lane} lane",
            )
            continue
        try:
            result = adapter.process(item)
            session.set_item_status(import_id, item["item_id"], result)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            session.set_item_status(import_id, item["item_id"], "failed", str(exc)[:500])
    final = "completed" if failed == 0 and processed else ("partial" if failed else "queued")
    session.finalize_session(import_id, processed=processed, failed=failed, status=final)
    return session.get_import(import_id)
