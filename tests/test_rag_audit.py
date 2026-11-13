"""R9 audit and RO-Crate tests."""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint
from services.rag_control import audit


class AuditRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_audit_adjudications(self) -> None:
        with mock.patch("routes.rag_control.list_adjudications", return_value=[{"adjudication_id": "a"}]):
            response = self.client.get("/api/rag/audit/adjudications")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["adjudications"][0]["adjudication_id"], "a")

    def test_adjudications_csv(self) -> None:
        with mock.patch("routes.rag_control.adjudications_csv", return_value="a,b\n1,2\n"):
            response = self.client.get("/api/rag/audit/adjudications.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.mimetype)

    def test_evidence_csv(self) -> None:
        with mock.patch("routes.rag_control.evidence_csv", return_value="a,b\n1,2\n"):
            response = self.client.get("/api/rag/multi/m/export/evidence.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))

    def test_ro_crate_route(self) -> None:
        with mock.patch("routes.rag_control.ro_crate", return_value=b"zip"):
            response = self.client.get("/api/rag/multi/m/export/ro-crate.zip")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")


class RoCrateTests(unittest.TestCase):
    def test_zip_contains_signed_finalization(self) -> None:
        run = {
            "multi_run_id": "multi_1",
            "query": "q",
            "groups": [],
            "adjudications": [],
            "conflicts": [],
            "duplicate_count": 0,
            "finalization": {"content_hash": "h", "signature": "s", "key_id": "k"},
        }
        with mock.patch("services.rag_control.audit.get_multi", return_value=run):
            blob = audit.ro_crate("multi_1")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            data = json.loads(archive.read("data/finalization.json"))
        self.assertEqual(data["signature"], "s")

    def test_zip_contains_metadata(self) -> None:
        run = {
            "multi_run_id": "multi_1",
            "query": "q",
            "groups": [
                {
                    "rag_id": "code",
                    "evidence": [
                        {
                            "evidence_id": "ev_1",
                            "content_hash": "h",
                            "source_path": "a.py",
                        }
                    ],
                }
            ],
            "adjudications": [],
            "conflicts": [],
            "duplicate_count": 0,
            "finalization": None,
        }
        with mock.patch("services.rag_control.audit.get_multi", return_value=run):
            blob = audit.ro_crate("multi_1")
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = set(archive.namelist())
            metadata = json.loads(archive.read("ro-crate-metadata.json"))
        self.assertIn("data/evidence.json", names)
        self.assertIn("data/finalization.json", names)
        self.assertEqual(metadata["@context"], "https://w3id.org/ro/crate/1.1/context")


if __name__ == "__main__":
    unittest.main()
