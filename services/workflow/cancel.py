"""Cooperative cancellation for workflow runs.

A run is cancelled by creating a ``CANCEL`` file inside its run directory. The
runner checks it between stages and stages can check it inside long loops (the
retrieve stage checks between sections).
"""

from __future__ import annotations

from pathlib import Path

CANCEL_FILENAME = "CANCEL"


class CancelledError(RuntimeError):
    """Raised by a stage when the run was cancelled by the user."""


def is_cancelled(run_dir: str | Path) -> bool:
    return (Path(run_dir) / CANCEL_FILENAME).exists()
