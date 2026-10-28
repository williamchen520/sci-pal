"""Webhook notification tests (no network)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import notifications, systematic


class WebhookTests(unittest.TestCase):
    def test_dispatch_and_filter(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        migrate(db)
        conn = sqlite3.connect(db)
        project = systematic.create_project(conn, "P")
        notifications.add_webhook(conn, project, "https://example.test/hook", "screened")
        notifications.add_webhook(conn, project, "https://example.test/all", "*")
        received = []
        delivered = notifications.notify(
            db, project, "screened", {"paper_id": "p1"}, sender=lambda hook, body: received.append(body)
        )
        conn.close()
        self.assertEqual(delivered, 2)
        self.assertEqual(received[0]["event"], "screened")

    def test_delete(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        migrate(db)
        conn = sqlite3.connect(db)
        project = systematic.create_project(conn, "P")
        hook_id = notifications.add_webhook(conn, project, "https://example.test/x")
        notifications.delete_webhook(conn, project, hook_id)
        self.assertEqual(notifications.list_webhooks(conn, project), [])
        conn.close()


if __name__ == "__main__":
    unittest.main()
