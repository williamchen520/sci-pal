"""Regression: unit ids must be scoped by library and snapshot."""

from __future__ import annotations

import unittest

from code_rag.ingest import scoped_unit_id


class ScopedUnitIdTests(unittest.TestCase):
    def test_same_path_two_libraries_do_not_collide(self) -> None:
        a = scoped_unit_id("lib_a", "snap_1", "unit_demo")
        b = scoped_unit_id("lib_b", "snap_1", "unit_demo")
        self.assertNotEqual(a, b)

    def test_same_input_is_stable(self) -> None:
        self.assertEqual(
            scoped_unit_id("lib_a", "snap_1", "unit_demo"),
            scoped_unit_id("lib_a", "snap_1", "unit_demo"),
        )

    def test_snapshot_changes_id(self) -> None:
        self.assertNotEqual(
            scoped_unit_id("lib_a", "snap_1", "unit_demo"),
            scoped_unit_id("lib_a", "snap_2", "unit_demo"),
        )


if __name__ == "__main__":
    unittest.main()
