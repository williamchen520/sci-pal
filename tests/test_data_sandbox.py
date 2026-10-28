"""Data sandbox: policy n>=10, redaction, artifacts, cloud gate."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

from services.data_sandbox import policy, session, store


def _make_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


class DataSandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        os.environ["SCIPAL_DATA_ROOT"] = str(Path(self.tmp.name) / "sandbox")
        os.environ["SCIPAL_MIN_AGG_N"] = "10"
        rows = []
        for index in range(12):
            rows.append({"sex": "F", "stage": "I", "name": f"P{index}", "age": 40 + index})
        for index in range(5):
            rows.append({"sex": "M", "stage": "II", "name": f"Q{index}", "age": 60 + index})
        self.csv = _make_csv(Path(self.tmp.name) / "cohort.csv", rows)
        self.frame = policy.load_table(self.csv)

    def test_classify_and_sensitive(self) -> None:
        self.assertEqual(policy.classify(self.csv), "raw")
        self.assertTrue(policy.is_sensitive_column("patient_name"))
        self.assertFalse(policy.is_sensitive_column("stage"))

    def test_profile_suppresses_small_counts(self) -> None:
        profile = policy.profile_frame(self.frame)
        sex = next(c for c in profile["columns"] if c["name"] == "sex")
        top = {item["value"]: item["n"] for item in sex["top_values"]}
        self.assertEqual(top["F"], 12)
        self.assertNotIn("M", top)  # n=5 suppressed

    def test_aggregate_suppression(self) -> None:
        result = policy.aggregate_frame(self.frame, ["sex"])
        self.assertEqual(len(result), 1)
        self.assertEqual(int(result.iloc[0]["n"]), 12)

    def test_sample_drops_sensitive(self) -> None:
        sample = policy.sample_frame(self.frame)
        self.assertLessEqual(len(sample), 5)
        self.assertNotIn("name", sample.columns)

    def test_artifacts_and_gate(self) -> None:
        store.create_project("alice", "proj1", str(self.csv), self.frame)
        profile = store.write_profile("alice", "proj1", self.frame)
        aggregate = store.write_aggregate("alice", "proj1", self.frame, ["sex"])
        sample = store.write_sample("alice", "proj1", self.frame)
        self.assertTrue(store.validate_artifact("alice", "proj1", profile["id"])["ok"])
        self.assertTrue(store.validate_artifact("alice", "proj1", aggregate["id"])["ok"])
        self.assertTrue(store.validate_artifact("alice", "proj1", sample["id"])["ok"])
        gate = store.cloud_gate("alice", "proj1", aggregate["id"])
        self.assertTrue(gate["allow"])

    def test_validate_catches_small_n(self) -> None:
        store.create_project("alice", "proj2", str(self.csv), self.frame)
        artifact = store.write_aggregate("alice", "proj2", self.frame, ["sex"])
        path = store.project_dir("alice", "proj2") / artifact["path"]
        path.write_text("sex,n\nF,12\nM,5\n", encoding="utf-8")
        result = store.validate_artifact("alice", "proj2", artifact["id"])
        self.assertFalse(result["ok"])
        self.assertTrue(any("below n" in reason for reason in result["reasons"]))

    def test_provider_allowlist(self) -> None:
        self.assertTrue(policy.provider_allowed("deepseek"))
        self.assertFalse(policy.provider_allowed("evil-cloud"))
        store.create_project("alice", "prov", str(self.csv), self.frame)
        artifact = store.write_aggregate("alice", "prov", self.frame, ["sex"])
        result = store.cloud_gate("alice", "prov", artifact["id"], "evil-cloud")
        self.assertFalse(result["allow"])
        self.assertIn("provider not allowed", result["reasons"])

    def test_session_templates(self) -> None:
        raw = session.open_session("raw")
        self.assertFalse(raw["cloud"])
        self.assertIn("data_profile", raw["tools"])
        public = session.open_session("public")
        self.assertTrue(public["cloud"])
        self.assertIn("search_evidence", public["tools"])

    def test_update_creates_new_version(self) -> None:
        store.create_project("alice", "proj3", str(self.csv), self.frame)
        artifact = store.write_aggregate("alice", "proj3", self.frame, ["sex"])
        new = store.update_artifact("alice", "proj3", artifact["id"], "sex,n\nF,12\n")
        self.assertNotEqual(new["id"], artifact["id"])
        self.assertEqual(new["supersedes"], artifact["id"])
        self.assertFalse(new["cloud_eligible"])


if __name__ == "__main__":
    unittest.main()
