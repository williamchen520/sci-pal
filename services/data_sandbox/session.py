"""Session templates: bind a data class to allowed models/tools before work."""

from __future__ import annotations

import uuid
from typing import Any, Dict

from services.data_sandbox import policy


def open_session(data_class: str) -> Dict[str, Any]:
    base = policy.session_policy(data_class)
    return {
        "session_id": f"sess_{uuid.uuid4().hex[:10]}",
        "data_class": data_class,
        "models": base["models"],
        "tools": base["tools"],
        "cloud": base["cloud"],
        "min_agg_n": policy.MIN_AGG_N,
        "max_sample_rows": policy.MAX_SAMPLE_ROWS,
        "serial": True,
    }
