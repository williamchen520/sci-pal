"""N0 import session validation tests."""

from __future__ import annotations

import unittest

from services.imports import session


class ImportSessionTests(unittest.TestCase):
    def test_empty_items_rejected(self) -> None:
        with self.assertRaises(session.ImportSessionError):
            session.create_import(tenant_id="default", library_id="lib", origin="manual", items=[])

    def test_invalid_origin_rejected(self) -> None:
        with self.assertRaises(session.ImportSessionError):
            session.create_import(
                tenant_id="default",
                library_id="lib",
                origin="cron",
                items=[{"uri": "a.pdf"}],
            )

    def test_missing_library_rejected(self) -> None:
        with self.assertRaises(session.ImportSessionError):
            session.create_import(
                tenant_id="default", library_id="", origin="manual", items=[{"uri": "a.pdf"}]
            )

    def test_too_many_items_rejected(self) -> None:
        with self.assertRaises(session.ImportSessionError):
            session.create_import(
                tenant_id="default",
                library_id="lib",
                origin="manual",
                items=[{"uri": "a.pdf"}] * 1001,
            )


if __name__ == "__main__":
    unittest.main()
