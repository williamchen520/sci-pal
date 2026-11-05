from __future__ import annotations

import unittest

from services.protocols.pg_import import _parse


class ProtocolPGImportTests(unittest.TestCase):
    def test_parse_payload(self):
        record, steps = _parse(
            {
                "protocol": {
                    "id": "p1",
                    "title": "T",
                    "steps": [{"id": "s1", "title": "S", "step": "do"}],
                }
            }
        )
        self.assertEqual(record["protocol_id"], "p1")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["step_id"], "s1")


if __name__ == "__main__":
    unittest.main()
