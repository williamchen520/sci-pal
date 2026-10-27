"""Model serialization: only one model slot at a time."""

from __future__ import annotations

import threading
import time
import unittest

from services.model_serial import active_count, model_slot


class ModelSerialTests(unittest.TestCase):
    def test_single_slot(self) -> None:
        peaks = []

        def worker() -> None:
            with model_slot("test", timeout=10):
                peaks.append(active_count())
                time.sleep(0.2)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(peaks, [1, 1, 1, 1])
        self.assertEqual(active_count(), 0)


if __name__ == "__main__":
    unittest.main()
