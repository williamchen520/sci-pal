"""Webhook notification tests (PostgreSQL mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from services.review import notifications


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakePG:
    def __init__(self, rows=None):
        self.rows = rows or []

    def execute(self, sql, params):
        if sql.strip().startswith("INSERT"):
            return Cursor(row={"id": 7})
        if sql.strip().startswith("SELECT"):
            return Cursor(rows=self.rows)
        return Cursor()

    def commit(self):
        pass

    def close(self):
        pass


class WebhookTests(unittest.TestCase):
    def test_add_returns_id(self) -> None:
        with mock.patch.object(notifications, "_pg", return_value=FakePG()):
            self.assertEqual(
                notifications.add_webhook(None, "p1", "https://example.test/x"), 7
            )

    def test_notify_filters_events(self) -> None:
        pg = FakePG(
            rows=[
                {"id": 1, "url": "a", "events": "screened", "secret": ""},
                {"id": 2, "url": "b", "events": "*", "secret": ""},
                {"id": 3, "url": "c", "events": "other", "secret": ""},
            ]
        )
        received = []
        with mock.patch.object(notifications, "_pg", return_value=pg):
            delivered = notifications.notify(
                "unused",
                "p1",
                "screened",
                {"paper_id": "p1"},
                sender=lambda hook, body: received.append(hook["url"]),
            )
        self.assertEqual(delivered, 2)
        self.assertEqual(received, ["a", "b"])

    def test_delete_calls_pg(self) -> None:
        pg = mock.Mock()
        pg.execute.return_value = Cursor()
        with mock.patch.object(notifications, "_pg", return_value=pg):
            notifications.delete_webhook(None, "p1", 3)
        pg.execute.assert_called_once()
        pg.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
