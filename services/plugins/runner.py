"""Plugin runner: schema validation + JSONL provenance.

M0 is trusted in-process execution. The contract already separates input/output
from the core so a subprocess adapter can be added without changing callers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema

from .contracts import (
    PluginExecutionError,
    PluginManifest,
    PluginRun,
    new_run_id,
    now_utc,
)
from .registry import PluginRegistry

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RUN_LOG = PROJECT_ROOT / "logs" / "plugin_runs.jsonl"


class PluginRunner:
    def __init__(
        self,
        registry: PluginRegistry,
        *,
        run_log: str | Path | None = None,
    ):
        self.registry = registry
        self.run_log = Path(run_log) if run_log is not None else DEFAULT_RUN_LOG

    def run(
        self,
        plugin_id: str,
        payload: Dict[str, Any],
        *,
        dataset_hash: str = "",
        seed: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> PluginRun:
        manifest: PluginManifest = self.registry.get(plugin_id)
        port = self.registry.get_port(manifest.port)
        config = config or {}
        started_at = now_utc()
        started = time.perf_counter()
        output: Optional[Dict[str, Any]] = None
        error: Optional[str] = None

        try:
            jsonschema.validate(instance=payload, schema=port.input_schema)
            adapter = self.registry.load_adapter(plugin_id)
            result = adapter.run(payload)
            if not isinstance(result, dict):
                raise PluginExecutionError("adapter.run() must return a dict")
            jsonschema.validate(instance=result, schema=port.output_schema)
            output = result
        except jsonschema.ValidationError as exc:
            error = f"schema: {exc.message}"
        except Exception as exc:  # noqa: BLE001 - recorded as a failed run
            error = f"{type(exc).__name__}: {exc}"

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        run = PluginRun(
            run_id=new_run_id(),
            plugin_id=manifest.id,
            plugin_version=manifest.version,
            port=manifest.port,
            dataset_hash=dataset_hash,
            seed=seed,
            config=config,
            input=payload,
            output=output,
            latency_ms=latency_ms,
            error=error,
            started_at=started_at,
        )
        self._append(run)
        if error:
            raise PluginExecutionError(f"{plugin_id}: {error}") from None
        return run

    def _append(self, run: PluginRun) -> None:
        self.run_log.parent.mkdir(parents=True, exist_ok=True)
        with self.run_log.open("a", encoding="utf-8") as handle:
            handle.write(run.to_json() + "\n")
