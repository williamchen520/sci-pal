"""M0 plugin infrastructure tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.plugins import (
    ManifestError,
    PluginExecutionError,
    PluginNotFound,
    PluginRegistry,
    PluginRunner,
)


class PluginInfraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "plugin_runs.jsonl"

    def test_registry_lists_echo(self) -> None:
        registry = PluginRegistry().load()
        ids = [item["id"] for item in registry.list_plugins()]
        self.assertIn("echo", ids)
        self.assertEqual(registry.get("echo").port, "echo")

    def test_runner_echo_and_log(self) -> None:
        runner = PluginRunner(PluginRegistry().load(), run_log=self.log)
        run = runner.run("echo", {"text": "hello"}, dataset_hash="sha256:demo", seed=1)
        self.assertEqual(run.output, {"echo": "hello", "length": 5})
        self.assertIsNone(run.error)
        rows = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plugin_id"], "echo")
        self.assertEqual(rows[0]["dataset_hash"], "sha256:demo")

    def test_invalid_input_is_recorded(self) -> None:
        runner = PluginRunner(PluginRegistry().load(), run_log=self.log)
        with self.assertRaises(PluginExecutionError):
            runner.run("echo", {"wrong": "field"})
        row = json.loads(self.log.read_text(encoding="utf-8").strip())
        self.assertIn("schema", row["error"])
        self.assertIsNone(row["output"])

    def test_unknown_plugin(self) -> None:
        with self.assertRaises(PluginNotFound):
            PluginRegistry().load().get("no-such-plugin")

    def test_missing_plugins_dir(self) -> None:
        with self.assertRaises(ManifestError):
            PluginRegistry(Path(self.tmp.name) / "nope").load()

    def test_manifest_requires_entrypoint_and_license(self) -> None:
        registry = PluginRegistry().load()
        manifest = registry.get("echo")
        self.assertTrue(manifest.entrypoint.endswith(":EchoPlugin"))
        self.assertEqual(manifest.license, "AGPL-3.0-only")


if __name__ == "__main__":
    unittest.main()
