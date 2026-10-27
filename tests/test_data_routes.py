"""Data sandbox HTTP routes."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.data import build_data_blueprint


class DataRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        os.environ["SCIPAL_DATA_ROOT"] = str(root / "sandbox")
        self.csv = root / "cohort.csv"
        with self.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sex", "name", "age"])
            for index in range(12):
                writer.writerow(["F", f"P{index}", 40 + index])
            for index in range(5):
                writer.writerow(["M", f"Q{index}", 60 + index])
        app = Flask(__name__)
        app.register_blueprint(build_data_blueprint(db_path=root / "x.db", log=app.logger))
        self.client = app.test_client()

    def test_profile_and_artifacts(self) -> None:
        response = self.client.post(
            "/api/data/profile",
            json={"path": str(self.csv), "project_id": "p1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["rows"], 17)
        artifacts = self.client.get(
            "/api/data/artifacts?project_id=p1"
        ).get_json()["artifacts"]
        self.assertEqual(len(artifacts), 2)
        gate = self.client.post(
            "/api/data/cloud-gate",
            json={"project_id": "p1", "artifact_id": body["sample"]["id"]},
        )
        self.assertTrue(gate.get_json()["allow"])

    def test_classify(self) -> None:
        body = self.client.get(f"/api/data/classify?path={self.csv}").get_json()
        self.assertEqual(body["data_class"], "raw")
        self.assertFalse(body["policy"]["cloud"])

    def test_aggregate_endpoint(self) -> None:
        response = self.client.post(
            "/api/data/aggregate",
            json={"path": str(self.csv), "project_id": "p2", "group_by": ["sex"]},
        )
        artifact = response.get_json()["artifact"]
        self.assertEqual(artifact["rows"], 1)
        self.assertEqual(artifact["min_cell_n"], 12)


if __name__ == "__main__":
    unittest.main()
