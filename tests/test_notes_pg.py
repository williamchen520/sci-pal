from __future__ import annotations

import os
import unittest
from unittest import mock

from services.notes import service


class NotesPGBackendTests(unittest.TestCase):
    def test_list_uses_pg(self):
        with mock.patch.dict(os.environ, {"SCIPAL_NOTES_BACKEND": "postgres"}):
            with mock.patch("services.notes.pg_service.list_notes", return_value=[]) as fn:
                self.assertEqual(service.list_notes("ws", "u", db_path="unused.db"), [])
        fn.assert_called_once()

    def test_create_uses_pg(self):
        with mock.patch.dict(os.environ, {"SCIPAL_NOTES_BACKEND": "postgres"}):
            with mock.patch(
                "services.notes.pg_service.create_note", return_value={"note_id": "n1"}
            ) as fn:
                self.assertEqual(
                    service.create_note("ws", "u", "x", db_path="unused.db"),
                    {"note_id": "n1"},
                )
        fn.assert_called_once()

    def test_delete_uses_pg(self):
        with mock.patch.dict(os.environ, {"SCIPAL_NOTES_BACKEND": "postgres"}):
            with mock.patch(
                "services.notes.pg_service.delete_note", return_value=True
            ) as fn:
                self.assertTrue(service.delete_note("n1", "ws", "u", db_path="unused.db"))
        fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
