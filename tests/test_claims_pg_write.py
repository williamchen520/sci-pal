from __future__ import annotations

import unittest
from unittest import mock

from services.claims import pg_write


class ClaimsPGWriteTests(unittest.TestCase):
    def test_add_evidence(self):
        with mock.patch.object(pg_write.pg_read, "get_claim", return_value={"claim_id": "c1"}):
            with mock.patch.object(
                pg_write,
                "_sentence",
                return_value={"paper_id": "p1", "text": "quote"},
            ):
                with mock.patch.object(pg_write.pg_writes, "add_evidence") as write:
                    with mock.patch.object(
                        pg_write.pg_read, "get_claim", return_value={"claim_id": "c1", "evidence": []}
                    ):
                        result = pg_write.add_evidence("c1", "s1", "supports")
        self.assertEqual(result["claim_id"], "c1")
        write.assert_called_once()

    def test_decide(self):
        with mock.patch.object(pg_write.pg_read, "get_claim", return_value={"claim_id": "c1"}):
            with mock.patch.object(pg_write.pg_writes, "update_claim") as write:
                pg_write.decide("c1", "accept")
        write.assert_called_once()

    def test_invalid_relation(self):
        with self.assertRaises(ValueError):
            pg_write.add_evidence("c1", "s1", "bad")


if __name__ == "__main__":
    unittest.main()
