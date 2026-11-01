"""PG-primary tenancy branches with SQLite mirror (no live PostgreSQL)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.tenancy import add_member, create_user, create_workspace, list_members
from services.tenancy import pg_writes


class PGTenancyMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "research.db"

    def test_enabled_flag(self):
        with mock.patch.dict(
            "os.environ",
            {"SCIPAL_TENANCY_WRITE_BACKEND": "postgres", "SCIPAL_PG_DSN": "postgresql://x"},
            clear=False,
        ):
            self.assertTrue(pg_writes.enabled())
        with mock.patch.dict("os.environ", {"SCIPAL_TENANCY_WRITE_BACKEND": ""}, clear=False):
            self.assertFalse(pg_writes.enabled())

    def test_create_user_pg_writes_and_mirrors_sqlite(self):
        pg_user = {
            "user_id": "user_pg1",
            "username": "pguser",
            "email": "p@example.org",
            "display_name": "PG User",
            "is_admin": False,
        }
        with mock.patch.object(pg_writes, "enabled", return_value=True), \
             mock.patch.object(pg_writes, "create_user", return_value=pg_user) as create:
            user = create_user("pguser", "long-enough-password", email="p@example.org", db_path=self.db)
        self.assertEqual(user["user_id"], "user_pg1")
        create.assert_called_once()
        rows = list_members("ws_missing", db_path=self.db)
        self.assertEqual(rows, [])
        import sqlite3
        conn = sqlite3.connect(self.db)
        try:
            row = conn.execute("SELECT username, is_admin FROM users WHERE user_id = ?", ("user_pg1",)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row, ("pguser", 0))

    def test_create_workspace_and_member_mirror(self):
        import sqlite3
        conn = sqlite3.connect(self.db)
        from services.tenancy.schema import ensure_schema
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO users (user_id, username, display_name, password_hash, status, is_admin) "
            "VALUES ('user_owner', 'owner', 'Owner', 'x', 'active', 0)"
        )
        conn.commit()
        conn.close()

        workspace = {
            "workspace_id": "ws_pg",
            "name": "PG Lab",
            "owner_user_id": "user_owner",
        }
        with mock.patch.object(pg_writes, "enabled", return_value=True), \
             mock.patch.object(pg_writes, "create_workspace", return_value=workspace):
            result = create_workspace("PG Lab", "user_owner", workspace_id="ws_pg", db_path=self.db)
        self.assertEqual(result["workspace_id"], "ws_pg")

        member = {
            "workspace_id": "ws_pg",
            "user_id": "user_owner",
            "role": "owner",
            "status": "active",
        }
        with mock.patch.object(pg_writes, "enabled", return_value=True), \
             mock.patch.object(pg_writes, "add_member", return_value=member):
            added = add_member("ws_pg", "user_owner", "owner", db_path=self.db)
        self.assertEqual(added.role, "owner")
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                conn.execute("SELECT role FROM memberships WHERE workspace_id='ws_pg' AND user_id='user_owner'").fetchone()[0],
                "owner",
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
