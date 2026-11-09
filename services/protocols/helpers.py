"""Pure helpers shared by protocol import/run adapters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping


RUN_STATUSES = ("planned", "running", "completed", "failed")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _run_status(value: Any) -> str:
    status = _text(value).lower() or "planned"
    return status if status in RUN_STATUSES else "planned"


def _done_steps(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def _run_row(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["done_steps"] = _done_steps(record.get("done_steps"))
    return record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _first(mapping: Mapping, *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return _text(value)
    return ""


def _normalize_protocol_id(value: Any) -> str:
    """Accept ``325000``, ``protocols_io_325000`` or a /view/...-325000 URL.

    URL slugs may contain digits before the real id (``western-blot-2024-325000``),
    so trailing digits win over the first digit group.
    """
    import re as re_lib

    text = str(value or "").strip()
    for pattern in (r"(\d+)\s*$", r"protocols_io_(\d+)", r"(\d{2,})"):
        match = re_lib.search(pattern, text)
        if match:
            return match.group(1)
    return text


def _html_text(value: Any) -> str:
    """API returns step bodies as HTML (``<p>...</p>``); strip tags for storage."""
    import html as html_lib
    import re as re_lib

    text = html_lib.unescape(str(value or ""))
    text = re_lib.sub(r"<[^>]+>", " ", text)
    return re_lib.sub(r"\s+", " ", text).strip()


def _duration(value: Any) -> str:
    text = _text(value)
    return "" if text in {"0", "0:00", "0.0"} else text


def _reagents(step: Mapping) -> list[str]:
    for key in ("reagents", "components", "materials", "reagents_list"):
        value = step.get(key)
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, Mapping):
                    result.append(_first(item, "name", "title", "reagent"))
                else:
                    result.append(_text(item))
            return [item for item in result if item]
    return []
