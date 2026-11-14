"""N0 orchestrator tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.imports import orchestrator
from services.imports.html_quality import QualityRejected


class _Paper:
    def process(self, item):
        return "draft"


class _Code:
    def process(self, item):
        return "indexed"


class _Fail:
    def process(self, item):
        raise RuntimeError("parse failed")


class _QualityFail:
    def process(self, item):
        raise QualityRejected("abstract too short")


class OrchestratorTests(unittest.TestCase):
    def _payload(self):
        return {
            "import_id": "imp_1",
            "items": [
                {"item_id": "i1", "source_kind": "pdf", "status": "detected"},
                {"item_id": "i2", "source_kind": "repo", "status": "detected"},
                {"item_id": "i3", "source_kind": "unknown", "status": "quarantined"},
            ],
        }

    def test_routes_and_processes(self) -> None:
        with mock.patch.object(orchestrator.session, "get_import", return_value=self._payload()), mock.patch.object(
            orchestrator.session, "set_item_status"
        ) as set_status, mock.patch.object(
            orchestrator.session, "finalize_session"
        ) as finalize:
            orchestrator.process_import("imp_1", paper_adapter=_Paper(), code_adapter=_Code())
        statuses = [call.args[2] for call in set_status.call_args_list]
        self.assertIn("draft", statuses)
        self.assertIn("indexed", statuses)
        self.assertTrue(finalize.called)

    def test_failure_is_isolated(self) -> None:
        with mock.patch.object(orchestrator.session, "get_import", return_value=self._payload()), mock.patch.object(
            orchestrator.session, "set_item_status"
        ) as set_status, mock.patch.object(
            orchestrator.session, "finalize_session"
        ) as finalize:
            orchestrator.process_import("imp_1", paper_adapter=_Fail(), code_adapter=_Code())
        failed = [call for call in set_status.call_args_list if call.args[2] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(finalize.call_args.kwargs["failed"], 1)

    def test_quality_reject_is_quarantined(self) -> None:
        with mock.patch.object(orchestrator.session, "get_import", return_value=self._payload()), mock.patch.object(
            orchestrator.session, "set_item_status"
        ) as set_status, mock.patch.object(orchestrator.session, "finalize_session"):
            orchestrator.process_import("imp_1", paper_adapter=_QualityFail())
        self.assertTrue(any(call.args[2] == "quarantined" for call in set_status.call_args_list))

    def test_no_adapter_stays_routed(self) -> None:
        with mock.patch.object(orchestrator.session, "get_import", return_value=self._payload()), mock.patch.object(
            orchestrator.session, "set_item_status"
        ) as set_status, mock.patch.object(orchestrator.session, "finalize_session"):
            orchestrator.process_import("imp_1")
        routed = [call for call in set_status.call_args_list if call.args[2] == "routed"]
        self.assertTrue(routed)


if __name__ == "__main__":
    unittest.main()
