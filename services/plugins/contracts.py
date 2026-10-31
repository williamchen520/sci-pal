"""Plugin port contracts and run records.

This is the M0 infrastructure layer: a plugin declares a manifest, the core
loads it, validates input/output against a port schema, and records one
``PluginRun`` per invocation. No plugin may write SciPal tables directly.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{1,80}$")
ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_][\w.]*$")
RUN_ID_PREFIX = "run_"


class PluginError(ValueError):
    """Base error for plugin infrastructure."""


class ManifestError(PluginError):
    """Invalid plugin manifest or port schema."""


class PluginNotFound(PluginError):
    """Unknown plugin id."""


class PluginExecutionError(PluginError):
    """Plugin failed, timed out, or returned an invalid payload."""


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return f"{RUN_ID_PREFIX}{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class PortSpec:
    """A core-owned port schema.

    The port id is referenced by ``PluginManifest.port``. Input/output are
    JSON Schema objects, validated by :class:`services.plugins.runner.PluginRunner`.
    """

    id: str
    version: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, source: str = "") -> "PortSpec":
        if not isinstance(data, dict):
            raise ManifestError(f"port must be an object: {source}")
        for key in ("id", "version", "input_schema", "output_schema"):
            if not data.get(key):
                raise ManifestError(f"port missing {key}: {source}")
        if not PLUGIN_ID_RE.match(str(data["id"])):
            raise ManifestError(f"invalid port id: {data['id']!r}")
        if not isinstance(data["input_schema"], dict) or not isinstance(
            data["output_schema"], dict
        ):
            raise ManifestError(f"port schemas must be objects: {source}")
        return cls(
            id=str(data["id"]),
            version=str(data["version"]),
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            description=str(data.get("description") or ""),
        )

    def summary(self) -> Dict[str, Any]:
        return {"id": self.id, "version": self.version, "description": self.description}


@dataclass(frozen=True)
class PluginManifest:
    id: str
    port: str
    version: str
    entrypoint: str
    license: str
    description: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, source: str = "") -> "PluginManifest":
        if not isinstance(data, dict):
            raise ManifestError(f"manifest must be an object: {source}")
        for key in ("id", "port", "version", "entrypoint", "license"):
            if not data.get(key):
                raise ManifestError(f"manifest missing {key}: {source}")
        if not PLUGIN_ID_RE.match(str(data["id"])):
            raise ManifestError(f"invalid plugin id: {data['id']!r}")
        if not PLUGIN_ID_RE.match(str(data["port"])):
            raise ManifestError(f"invalid port id: {data['port']!r}")
        if not ENTRYPOINT_RE.match(str(data["entrypoint"])):
            raise ManifestError(
                f"invalid entrypoint (expected module:Class): {data['entrypoint']!r}"
            )
        capabilities = data.get("capabilities") or {}
        runtime = data.get("runtime") or {}
        if not isinstance(capabilities, dict) or not isinstance(runtime, dict):
            raise ManifestError(f"capabilities/runtime must be objects: {source}")
        return cls(
            id=str(data["id"]),
            port=str(data["port"]),
            version=str(data["version"]),
            entrypoint=str(data["entrypoint"]),
            license=str(data["license"]),
            description=str(data.get("description") or ""),
            capabilities=capabilities,
            runtime=runtime,
            path=str(source) if source else None,
        )

    @property
    def module(self) -> str:
        return self.entrypoint.split(":", 1)[0]

    @property
    def class_name(self) -> str:
        return self.entrypoint.split(":", 1)[1]

    def summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "port": self.port,
            "version": self.version,
            "license": self.license,
            "description": self.description,
            "capabilities": self.capabilities,
        }


@dataclass
class PluginRun:
    """One plugin invocation, suitable for JSONL provenance."""

    run_id: str
    plugin_id: str
    plugin_version: str
    port: str
    dataset_hash: str
    seed: Optional[int]
    config: Dict[str, Any]
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    latency_ms: float
    error: Optional[str] = None
    started_at: str = field(default_factory=now_utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "port": self.port,
            "dataset_hash": self.dataset_hash,
            "seed": self.seed,
            "config": self.config,
            "input": self.input,
            "output": self.output,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "started_at": self.started_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


# The plan calls this a "PortContract"; the concrete schema object is PortSpec.
PortContract = PortSpec
