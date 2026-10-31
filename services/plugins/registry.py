"""Plugin discovery and manifest validation.

The registry only reads manifests/port schemas and imports declared adapters.
It does not execute arbitrary code paths outside the declared entrypoint.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .contracts import (
    ManifestError,
    PluginManifest,
    PluginNotFound,
    PortSpec,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PLUGINS_DIR = PROJECT_ROOT / "plugins"


def plugins_dir() -> Path:
    return Path(os.environ.get("SCIPAL_PLUGINS_DIR") or DEFAULT_PLUGINS_DIR)


class PluginRegistry:
    """Load ``plugins/manifests/*.yaml`` and ``plugins/ports/*.json``."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else plugins_dir()
        self._plugins: Dict[str, PluginManifest] = {}
        self._ports: Dict[str, PortSpec] = {}
        self._loaded = False

    # ------------------------------------------------------------------ load
    def load(self) -> "PluginRegistry":
        manifests_dir = self.root / "manifests"
        ports_dir = self.root / "ports"
        if not manifests_dir.is_dir():
            raise ManifestError(f"missing manifests dir: {manifests_dir}")
        if not ports_dir.is_dir():
            raise ManifestError(f"missing ports dir: {ports_dir}")

        ports: Dict[str, PortSpec] = {}
        for path in sorted(ports_dir.glob("*.json")):
            data = self._read_json(path)
            spec = PortSpec.from_dict(data, source=str(path))
            if spec.id in ports:
                raise ManifestError(f"duplicate port id: {spec.id}")
            ports[spec.id] = spec

        plugins: Dict[str, PluginManifest] = {}
        for path in sorted(manifests_dir.glob("*.yaml")):
            data = self._read_yaml(path)
            manifest = PluginManifest.from_dict(data, source=str(path))
            if manifest.id in plugins:
                raise ManifestError(f"duplicate plugin id: {manifest.id}")
            if manifest.port not in ports:
                raise ManifestError(
                    f"plugin {manifest.id!r} references unknown port {manifest.port!r}"
                )
            plugins[manifest.id] = manifest

        self._plugins = plugins
        self._ports = ports
        self._loaded = True
        return self

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ManifestError(f"cannot read {path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise ManifestError(f"expected JSON object: {path.name}")
        return data

    @staticmethod
    def _read_yaml(path: Path) -> Dict[str, Any]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ManifestError(f"cannot read {path.name}: {exc}") from exc
        if not isinstance(data, dict):
            raise ManifestError(f"expected YAML object: {path.name}")
        return data

    # --------------------------------------------------------------- access
    def list_plugins(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return [self._plugins[key].summary() for key in sorted(self._plugins)]

    def get(self, plugin_id: str) -> PluginManifest:
        self._ensure_loaded()
        manifest = self._plugins.get(plugin_id)
        if manifest is None:
            raise PluginNotFound(f"unknown plugin: {plugin_id}")
        return manifest

    def get_port(self, port_id: str) -> PortSpec:
        self._ensure_loaded()
        spec = self._ports.get(port_id)
        if spec is None:
            raise PluginNotFound(f"unknown port: {port_id}")
        return spec

    def load_adapter(self, plugin_id: str) -> Any:
        """Import and instantiate the declared adapter class."""
        manifest = self.get(plugin_id)
        try:
            module = importlib.import_module(manifest.module)
        except ImportError as exc:
            raise ManifestError(
                f"cannot import {manifest.module!r} for plugin {plugin_id!r}: {exc}"
            ) from exc
        try:
            cls = getattr(module, manifest.class_name)
        except AttributeError as exc:
            raise ManifestError(
                f"entrypoint class missing: {manifest.entrypoint}"
            ) from exc
        try:
            adapter = cls()
        except Exception as exc:  # noqa: BLE001 - surface a manifest-level error
            raise ManifestError(f"cannot instantiate {manifest.entrypoint}: {exc}") from exc
        if not callable(getattr(adapter, "run", None)):
            raise ManifestError(f"adapter has no run(): {manifest.entrypoint}")
        return adapter

    def summary(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return {
            "root": str(self.root),
            "plugins": self.list_plugins(),
            "ports": [spec.summary() for spec in sorted(self._ports.values(), key=lambda x: x.id)],
        }
