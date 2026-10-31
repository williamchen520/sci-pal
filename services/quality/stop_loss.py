"""Stop-loss guard for tests and dataset metrics.

Rule 4 of .dsh_rules: after two consecutive negative results, stop tuning and
wait for a human. This module persists counters in a JSON state file so the
limit applies across separate script invocations, not only within one run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

STOP_MESSAGE = "触发止损规则，停止调参，等待人类介入"
DEFAULT_STATE = Path("logs") / "stop_loss_state.json"


class StopLossTriggered(RuntimeError):
    """Raised when the same negative result reaches the configured limit."""

    def __init__(self, kind: str, name: str, count: int, limit: int):
        self.kind = kind
        self.name = name
        self.count = count
        self.limit = limit
        super().__init__(f"{STOP_MESSAGE} [{kind}: {name} {count}/{limit}]")


class StopLossGuard:
    def __init__(self, state_path: str | Path = DEFAULT_STATE, limit: int = 2):
        self.state_path = Path(state_path)
        self.limit = max(1, int(limit))
        self.state = self._load()

    # ------------------------------------------------------------------ state
    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"tests": {}, "metrics": {}}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"tests": {}, "metrics": {}}
        if not isinstance(data, dict):
            return {"tests": {}, "metrics": {}}
        data.setdefault("tests", {})
        data.setdefault("metrics", {})
        return data

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.state_path)

    # ------------------------------------------------------------------ tests
    def record_test(self, test_id: str, passed: bool) -> int:
        """Record one test outcome; raise after ``limit`` consecutive failures."""
        entry = self.state["tests"].setdefault(test_id, {"consecutive_failures": 0})
        if passed:
            entry["consecutive_failures"] = 0
        else:
            entry["consecutive_failures"] = int(entry.get("consecutive_failures") or 0) + 1
        self._save()
        count = entry["consecutive_failures"]
        if count >= self.limit:
            raise StopLossTriggered("test", test_id, count, self.limit)
        return count

    # ---------------------------------------------------------------- metrics
    def record_metric(
        self,
        name: str,
        value: float,
        *,
        direction: str = "max",
        tolerance: float = 0.0,
    ) -> int:
        """Record a metric; raise after ``limit`` consecutive non-improvements.

        First observation establishes a baseline and never counts as a negative.
        ``direction=max`` means higher is better; ``min`` means lower is better.
        """
        if direction not in {"max", "min"}:
            raise ValueError("direction must be 'max' or 'min'")
        entry = self.state["metrics"].setdefault(
            name, {"last_value": None, "direction": direction, "consecutive_non_improvements": 0}
        )
        previous = entry.get("last_value")
        entry["direction"] = direction
        if previous is None:
            entry["last_value"] = float(value)
            entry["consecutive_non_improvements"] = 0
            self._save()
            return 0
        improved = (
            float(value) > float(previous) + float(tolerance)
            if direction == "max"
            else float(value) < float(previous) - float(tolerance)
        )
        entry["consecutive_non_improvements"] = 0 if improved else int(
            entry.get("consecutive_non_improvements") or 0
        ) + 1
        entry["last_value"] = float(value)
        self._save()
        count = entry["consecutive_non_improvements"]
        if count >= self.limit:
            raise StopLossTriggered("metric", name, count, self.limit)
        return count

    # ------------------------------------------------------------------ reset
    def reset(self) -> None:
        self.state = {"tests": {}, "metrics": {}}
        self._save()
