from __future__ import annotations

import json
import os
import time
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_backup_loop import choose_scope, prune


class BackupPolicyTests(unittest.TestCase):
    def test_first_run_is_full_then_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertEqual(choose_scope(out, 7), "full")
            (out / "backup_state.json").write_text(
                json.dumps({"last_full_at": datetime.now(timezone.utc).isoformat()}),
                encoding="utf-8",
            )
            self.assertEqual(choose_scope(out, 7), "db")

    def test_prune_is_scope_specific(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            old_db = out / "scipal-db-20200101-000000.tar.gz"
            old_full = out / "scipal-full-20200101-000000.tar.gz"
            old_db.write_text("db", encoding="utf-8")
            old_full.write_text("full", encoding="utf-8")
            old = time.time() - 40 * 86400
            os.utime(old_db, (old, old))
            os.utime(old_full, (old, old))
            removed = prune(out, "db", 30)
            self.assertEqual(removed, [old_db.name])
            self.assertTrue(old_full.exists())


if __name__ == "__main__":
    unittest.main()
