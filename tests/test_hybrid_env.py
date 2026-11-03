from __future__ import annotations

import unittest
from unittest.mock import patch

from services.search.hybrid_search import _env_flag, _env_int


class HybridEnvTests(unittest.TestCase):
    def test_flag(self):
        with patch.dict("os.environ", {"SCIPAL_MULTI_QUERY": "0"}):
            self.assertFalse(_env_flag("SCIPAL_MULTI_QUERY", True))
        with patch.dict("os.environ", {"SCIPAL_MULTI_QUERY": "yes"}):
            self.assertTrue(_env_flag("SCIPAL_MULTI_QUERY", False))

    def test_int_clamped(self):
        with patch.dict("os.environ", {"SCIPAL_MAX_QUERY_VARIANTS": "9"}):
            self.assertEqual(_env_int("SCIPAL_MAX_QUERY_VARIANTS", 4, low=1, high=4), 4)
        with patch.dict("os.environ", {"SCIPAL_MAX_QUERY_VARIANTS": "bad"}):
            self.assertEqual(_env_int("SCIPAL_MAX_QUERY_VARIANTS", 4, low=1, high=4), 4)


if __name__ == "__main__":
    unittest.main()
