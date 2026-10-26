"""Cross-system task lookup.

SciPal has several task stores (unified tasks, review tasks, export tasks, ingest
tasks). Their ids never collide, but callers only know the id. This module gives
one lookup that tries each store and reports which one owned the task.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


def lookup_task(
    task_id: str,
    *,
    unified: Callable[[str], Any] | None = None,
    review: Callable[[str], Any] | None = None,
    export: Callable[[str], Any] | None = None,
    ingest: Callable[[str], Any] | None = None,
) -> dict[str, Any] | None:
    """Return ``{"source": ..., "task": ...}`` for the first store that knows the id."""
    for source, getter in (
        ("unified", unified or _unified_get),
        ("review", review or _review_get),
        ("export", export or _export_get),
        ("ingest", ingest or _ingest_get),
    ):
        try:
            task = getter(task_id)
        except Exception:  # noqa: BLE001 - a broken store must not hide the others
            continue
        if task:
            if hasattr(task, "to_dict"):
                task = task.to_dict()
            return {"source": source, "task": task}
    return None


def _unified_get(task_id: str):
    from services.unified_task_manager import get_task

    return get_task(task_id)


def _review_get(task_id: str):
    from services.review.task_manager import task_manager

    return task_manager.get_task(task_id)


def _export_get(task_id: str):
    from services.review.export_manager import get_export_manager

    return get_export_manager().get_task(task_id)


def _ingest_get(task_id: str):
    from services.search.ingest import IngestService

    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    service = IngestService(
        db_path=root / "data" / "research.db",
        xml_dir=root / "documents_xml",
        chroma_path=root / "data" / "chroma",
        log=lambda _: None,
    )
    return service.status(task_id)
