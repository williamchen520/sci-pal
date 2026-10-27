"""End-to-end: CSV -> profile/aggregate -> validate -> gate -> send -> audit."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

from services.data_sandbox import audit, store


class DataE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        os.environ["SCIPAL_DATA_ROOT"] = str(root / "sandbox")
        os.environ["SCIPAL_AUDIT_DB"] = str(root / "audit.db")
        os.environ["SCIPAL_MIN_AGG_N"] = "10"
        self.csv = root / "cohort.csv"
        with self.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sex", "name", "age"])
            for index in range(12):
                writer.writerow(["F", f"P{index}", 40 + index])
            for index in range(5):
                writer.writerow(["M", f"Q{index}", 60 + index])
        from services.data_sandbox import policy

        self.frame = policy.load_table(self.csv)

    def test_full_flow_and_audit(self) -> None:
        store.create_project("alice", "e2e", str(self.csv), self.frame)
        store.write_profile("alice", "e2e", self.frame)
        aggregate = store.write_aggregate("alice", "e2e", self.frame, ["sex"])
        self.assertTrue(store.validate_artifact("alice", "e2e", aggregate["id"])["ok"])
        self.assertTrue(store.cloud_gate("alice", "e2e", aggregate["id"], "deepseek")["allow"])
        self.assertTrue(
            store.log_cloud_send("alice", "e2e", aggregate["id"], "deepseek")["allow"]
        )

        events = audit.list_events("alice", "e2e")
        actions = {event["action"] for event in events}
        self.assertIn("project_created", actions)
        self.assertIn("artifact_created", actions)
        self.assertIn("artifact_validated", actions)
        self.assertIn("cloud_gate_allowed", actions)
        self.assertIn("cloud_send", actions)
        send = next(event for event in events if event["action"] == "cloud_send")
        self.assertEqual(send["provider"], "deepseek")
        self.assertTrue(send["sha256"])
        # no raw cells or source filenames in audit details
        joined = " ".join(event.get("detail") or "" for event in events)
        self.assertNotIn("P0", joined)
        self.assertNotIn("Q0", joined)
        self.assertNotIn("cohort.csv", joined)

    def test_denied_gate_is_audited(self) -> None:
        store.create_project("bob", "e2e2", str(self.csv), self.frame)
        artifact = store.write_aggregate("bob", "e2e2", self.frame, ["sex"])
        path = store.project_dir("bob", "e2e2") / artifact["path"]
        path.write_text("sex,n\nF,12\nM,5\n", encoding="utf-8")
        result = store.cloud_gate("bob", "e2e2", artifact["id"], "openai")
        self.assertFalse(result["allow"])
        events = audit.list_events("bob", "e2e2")
        self.assertTrue(any(e["action"] == "cloud_gate_denied" for e in events))


if __name__ == "__main__":
    unittest.main()
