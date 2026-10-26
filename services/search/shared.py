"""Process-wide shared ``HybridSearch``.

Before this module, ``UnifiedRetriever`` constructed its own ``HybridSearch``
and ``api_server.get_hybrid()`` constructed a second one — two embedding models
and two Chroma handles per process (T-5 diagnostics measured +9.7 s and roughly
one extra model's memory). Both now go through :func:`get_shared_hybrid`.
"""

from __future__ import annotations

from typing import Any, Callable

from services.search.hybrid_search import HybridSearch

_SHARED: Any | None = None


def get_shared_hybrid(
    diagnostics: bool = False,
    factory: Callable[..., Any] | None = None,
) -> Any:
    """Return the single HybridSearch instance, creating it on first use."""
    global _SHARED
    if _SHARED is None:
        builder = factory or HybridSearch
        _SHARED = builder(diagnostics=diagnostics)
    return _SHARED


def reset_shared_hybrid() -> None:
    """Drop the cached instance (tests / config changes)."""
    global _SHARED
    _SHARED = None
