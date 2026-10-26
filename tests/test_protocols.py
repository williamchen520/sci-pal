"""protocols.io P1: payload parsing, storage and routes (fixtures, no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.protocols import build_protocols_blueprint
from services.protocols.service import ProtocolService

FIXTURE = {
    "status_code": 0,
    "protocol": {
        "id": "px_test_001",
        "title": "TLR4 stimulation assay",
        "doi": "10.17504/protocols.io.test001",
        "version": "3",
        "license": "CC-BY 4.0",
        "steps": [
            {
                "id": "s1",
                "title": "Seed macrophages",
                "description": "Seed 1e6 cells per well in 6-well plates.",
                "duration": "1 day",
                "reagents": [{"name": "RPMI-1640"}, {"name": "FBS"}],
            },
            {
                "id": "s2",
                "title": "Stimulate with LPS",
                "instructions": "Add LPS to 100 ng/mL for 6 h.",
                "time": "6 h",
            },
        ],
    },
}


class ProtocolServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.service = ProtocolService(Path(self.tmp.name) / "p.db")

    def test_import_payload_stores_steps(self) -> None:
        result = self.service.import_payload(FIXTURE)
        self.assertEqual(result["protocol_id"], "px_test_001")
        self.assertEqual(result["steps"], 2)

    def test_get_returns_ordered_steps_and_reagents(self) -> None:
        self.service.import_payload(FIXTURE)
        record = self.service.get("px_test_001")
        self.assertEqual(record["title"], "TLR4 stimulation assay")
        titles = [step["title"] for step in record["steps"]]
        self.assertEqual(titles, ["Seed macrophages", "Stimulate with LPS"])
        self.assertIn("RPMI-1640", record["steps"][0]["reagents"])
        self.assertEqual(record["steps"][1]["duration"], "6 h")

    def test_list_returns_summary_with_step_count(self) -> None:
        self.service.import_payload(FIXTURE)
        rows = self.service.list()
        self.assertEqual(rows[0]["protocol_id"], "px_test_001")
        self.assertEqual(rows[0]["steps"], 2)

    def test_missing_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.service.import_payload({"protocol": {}})

    def test_import_without_client_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            self.service.import_protocol("px_test_001")

    def test_attachment_roundtrip(self) -> None:
        self.service.import_payload(FIXTURE)
        run = self.service.add_run("px_test_001", title="Run")
        record = self.service.add_attachment(
            run["run_id"], "result.png", "image/png", b"png-bytes"
        )
        files = self.service.list_attachments(run["run_id"])
        self.assertEqual(files[0]["filename"], "result.png")
        path = self.service.attachment_path(run["run_id"], record["file_id"])
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertTrue(self.service.delete_attachment(run["run_id"], record["file_id"]))
        self.assertFalse(path.exists())

    def test_attachment_rejects_missing_run(self) -> None:
        with self.assertRaises(ValueError):
            self.service.add_attachment("run_nope", "a.txt", "text/plain", b"x")

    def test_attachment_rejects_oversize(self) -> None:
        self.service.import_payload(FIXTURE)
        run = self.service.add_run("px_test_001", title="Run")
        original = self.service.MAX_ATTACHMENT_BYTES
        self.service.MAX_ATTACHMENT_BYTES = 4
        self.addCleanup(setattr, self.service, "MAX_ATTACHMENT_BYTES", original)
        with self.assertRaises(ValueError):
            self.service.add_attachment(run["run_id"], "big.bin", "application/octet-stream", b"12345")

    def test_attachment_run_quota(self) -> None:
        self.service.import_payload(FIXTURE)
        run = self.service.add_run("px_test_001", title="Run")
        original = self.service.MAX_RUN_ATTACHMENT_BYTES
        self.service.MAX_RUN_ATTACHMENT_BYTES = 6
        self.addCleanup(setattr, self.service, "MAX_RUN_ATTACHMENT_BYTES", original)
        self.service.add_attachment(run["run_id"], "a.txt", "text/plain", b"1234")
        with self.assertRaises(ValueError):
            self.service.add_attachment(run["run_id"], "b.txt", "text/plain", b"123")

    def test_html_step_is_stripped_and_zero_duration_dropped(self) -> None:
        payload = {
            "protocol": {
                "id": "px_html",
                "title": "HTML protocol",
                "steps": [
                    {"id": "a", "step": "<p>Wash <b>3x</b> with PBS.</p>", "duration": "0"},
                ],
            }
        }
        self.service.import_payload(payload)
        step = self.service.get("px_html")["steps"][0]
        self.assertEqual(step["instructions"], "Wash 3x with PBS.")
        self.assertEqual(step["duration"], "")

    def test_prefixed_protocol_id_is_normalized(self) -> None:
        captured = {}

        class FakeClient:
            def fetch_protocol(self, protocol_id):
                captured["id"] = protocol_id
                return {"protocol": {"id": protocol_id, "title": "t", "steps": []}}

        service = ProtocolService(Path(self.tmp.name) / "p2.db", client=FakeClient())
        service.import_protocol("protocols_io_325000")
        self.assertEqual(captured["id"], "325000")

    def test_view_url_with_digits_in_slug(self) -> None:
        from services.protocols.service import _normalize_protocol_id

        cases = {
            "325000": "325000",
            "protocols_io_325000": "325000",
            "https://www.protocols.io/view/western-blot-2024-325000": "325000",
            "https://www.protocols.io/view/abc-123456": "123456",
        }
        for raw, expected in cases.items():
            self.assertEqual(_normalize_protocol_id(raw), expected, raw)


class FakeService:
    def __init__(self, service: ProtocolService) -> None:
        self.service = service

    def import_payload(self, payload, url=""):
        return self.service.import_payload(payload, url=url)

    def import_protocol(self, protocol_id):
        raise RuntimeError("no token")

    def list(self, limit=50, offset=0, query=""):
        return self.service.list(limit, offset, query)

    def count(self, query=""):
        return self.service.count(query)

    def get(self, protocol_id):
        return self.service.get(protocol_id)

    def add_run(self, protocol_id, **kwargs):
        return self.service.add_run(protocol_id, **kwargs)

    def list_runs(self, protocol_id, limit=50):
        return self.service.list_runs(protocol_id, limit)

    def recent_runs(self, limit=20):
        return self.service.recent_runs(limit)

    def update_run(self, run_id, **fields):
        return self.service.update_run(run_id, **fields)

    def delete_run(self, run_id):
        return self.service.delete_run(run_id)

    def export_markdown(self, protocol_id):
        return self.service.export_markdown(protocol_id)

    def add_attachment(self, run_id, filename, content_type, data):
        return self.service.add_attachment(run_id, filename, content_type, data)

    def list_attachments(self, run_id):
        return self.service.list_attachments(run_id)

    def attachment_path(self, run_id, file_id):
        return self.service.attachment_path(run_id, file_id)

    def delete_attachment(self, run_id, file_id):
        return self.service.delete_attachment(run_id, file_id)


class ProtocolRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.service = ProtocolService(Path(self.tmp.name) / "p.db")
        app = Flask(__name__)
        fake = FakeService(self.service)
        app.register_blueprint(build_protocols_blueprint(get_service=lambda: fake, log=app.logger))
        self.client = app.test_client()

    def test_import_payload_endpoint(self) -> None:
        response = self.client.post("/api/protocols/import", json={"payload": FIXTURE})
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["steps"], 2)

    def test_import_without_token_returns_400(self) -> None:
        response = self.client.post("/api/protocols/import", json={"protocol_id": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("token", response.get_json()["error"])

    def test_list_and_detail(self) -> None:
        self.client.post("/api/protocols/import", json={"payload": FIXTURE})
        listing = self.client.get("/api/protocols").get_json()
        self.assertEqual(listing["count"], 1)
        self.assertEqual(listing["total"], 1)

    def test_list_filters_by_query(self) -> None:
        self.client.post("/api/protocols/import", json={"payload": FIXTURE})
        other = {
            "protocol": {"id": "px_other", "title": "Western blot", "steps": []}
        }
        self.client.post("/api/protocols/import", json={"payload": other})
        listing = self.client.get("/api/protocols?q=TLR4").get_json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["protocols"][0]["protocol_id"], "px_test_001")
        detail = self.client.get("/api/protocols/px_test_001").get_json()
        self.assertEqual(len(detail["protocol"]["steps"]), 2)

    def test_missing_protocol_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/protocols/nope").status_code, 404)

    def test_experiment_run_lifecycle(self) -> None:
        self.client.post("/api/protocols/import", json={"payload": FIXTURE})
        created = self.client.post(
            "/api/protocols/px_test_001/runs",
            json={"title": "Run 1", "operator": "chen", "status": "running", "result": ""},
        )
        self.assertEqual(created.status_code, 200)
        run = created.get_json()["run"]
        self.assertEqual(run["status"], "running")

        listed = self.client.get("/api/protocols/px_test_001/runs").get_json()
        self.assertEqual(listed["count"], 1)

        updated = self.client.patch(
            f"/api/experiments/{run['run_id']}",
            json={"status": "completed", "result": "OK", "done_steps": ["s1", "s2"]},
        ).get_json()
        self.assertEqual(updated["run"]["status"], "completed")
        self.assertEqual(updated["run"]["done_steps"], ["s1", "s2"])

        recent = self.client.get("/api/experiments").get_json()
        self.assertEqual(recent["runs"][0]["protocol_title"], "TLR4 stimulation assay")

        self.assertEqual(self.client.delete(f"/api/experiments/{run['run_id']}").status_code, 200)
        self.assertEqual(self.client.get("/api/protocols/px_test_001/runs").get_json()["count"], 0)

    def test_run_for_missing_protocol_returns_404(self) -> None:
        self.assertEqual(
            self.client.post("/api/protocols/nope/runs", json={"title": "x"}).status_code, 404
        )

    def test_export_markdown_contains_steps_and_runs(self) -> None:
        self.client.post("/api/protocols/import", json={"payload": FIXTURE})
        self.client.post(
            "/api/protocols/px_test_001/runs",
            json={"title": "Run A", "operator": "chen", "done_steps": ["s1"]},
        )
        response = self.client.get("/api/protocols/px_test_001/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["Content-Type"])
        body = response.get_data(as_text=True)
        self.assertIn("TLR4 stimulation assay", body)
        self.assertIn("Seed macrophages", body)
        self.assertIn("Run A", body)
        self.assertIn("1/2", body)

    def test_export_missing_protocol_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/protocols/nope/export").status_code, 404)

    def test_attachment_routes_roundtrip(self) -> None:
        import io

        self.client.post("/api/protocols/import", json={"payload": FIXTURE})
        run = self.client.post(
            "/api/protocols/px_test_001/runs", json={"title": "R"}
        ).get_json()["run"]
        uploaded = self.client.post(
            f"/api/experiments/{run['run_id']}/attachments",
            data={"file": (io.BytesIO(b"raw-data"), "result.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 200)
        file_id = uploaded.get_json()["file"]["file_id"]

        listed = self.client.get(
            f"/api/experiments/{run['run_id']}/attachments"
        ).get_json()
        self.assertEqual(listed["count"], 1)

        downloaded = self.client.get(
            f"/api/experiments/{run['run_id']}/attachments/{file_id}"
        )
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.data, b"raw-data")
        downloaded.close()

        deleted = self.client.delete(
            f"/api/experiments/{run['run_id']}/attachments/{file_id}"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/experiments/{run['run_id']}/attachments")
            .get_json()["count"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
