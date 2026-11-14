"""Paper code-library binding tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import bindings


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Conn:
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.committed = False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        return _Cursor(self.row)

    def commit(self):
        self.committed = True

    def close(self):
        return None


class BindingTests(unittest.TestCase):
    def test_binding_id_stable(self) -> None:
        first = bindings._binding_id("p1", "l1")
        second = bindings._binding_id("p1", "l1")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("bind_"))

    def test_bind_link(self) -> None:
        corpus = _Conn({"link_id": "l1", "paper_id": "p1", "url": "https://github.com/a/b"})
        owner = _Conn()
        with mock.patch.object(bindings, "corpus_connection", return_value=corpus), mock.patch.object(
            bindings, "owner_connection", return_value=owner
        ), mock.patch.object(bindings, "_lookup_snapshot", return_value="snap_1"):
            binding = bindings.bind_link("p1", "l1", library_id="lib_abc")
        self.assertEqual(binding["status"], "bound")
        self.assertEqual(binding["snapshot_id"], "snap_1")
        self.assertTrue(owner.committed)

    def test_bind_rejects_bad_library(self) -> None:
        with self.assertRaises(ValueError):
            bindings.bind_link("p1", "l1", library_id="scanpy")


if __name__ == "__main__":
    unittest.main()
