"""Tenancy primitives: local accounts, workspaces, roles."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.tenancy import (
    TenancyError,
    add_member,
    authenticate,
    authorize,
    bootstrap_default_workspace,
    create_user,
    create_workspace,
    ensure_schema,
    get_membership,
    list_members,
)
from services.tenancy.service import hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_hash_is_not_plaintext_and_verifies(self) -> None:
        encoded = hash_password("correct horse battery")
        self.assertNotIn("correct horse", encoded)
        self.assertTrue(verify_password("correct horse battery", encoded))
        self.assertFalse(verify_password("wrong password", encoded))

    def test_short_password_rejected(self) -> None:
        with self.assertRaises(TenancyError):
            hash_password("short")

    def test_malformed_hash_rejected(self) -> None:
        self.assertFalse(verify_password("anything", "not-a-hash"))
        self.assertFalse(verify_password("anything", None))


class TenancyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "research.db"

    def test_schema_is_idempotent_and_adds_user_columns(self) -> None:
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, "
            "email TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute("INSERT INTO users (user_id, username) VALUES ('legacy', 'legacy')")
        conn.commit()
        ensure_schema(conn)
        ensure_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        self.assertTrue({"password_hash", "display_name", "status", "is_admin"} <= columns)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
        conn.close()

    def test_create_and_authenticate(self) -> None:
        user = create_user("alice", "long-enough-password", email="a@example.org", db_path=self.db)
        self.assertEqual(user["username"], "alice")
        self.assertEqual(authenticate("alice", "long-enough-password", db_path=self.db)["user_id"], user["user_id"])
        self.assertIsNone(authenticate("alice", "bad", db_path=self.db))
        self.assertIsNone(authenticate("nobody", "long-enough-password", db_path=self.db))

    def test_duplicate_user_rejected(self) -> None:
        create_user("alice", "long-enough-password", db_path=self.db)
        with self.assertRaises(TenancyError):
            create_user("alice", "another-password", db_path=self.db)

    def test_invalid_username_and_email(self) -> None:
        with self.assertRaises(TenancyError):
            create_user("a", "long-enough-password", db_path=self.db)
        with self.assertRaises(TenancyError):
            create_user("alice", "long-enough-password", email="bad", db_path=self.db)

    def test_create_workspace_owner_membership(self) -> None:
        owner = create_user("owner", "long-enough-password", db_path=self.db)
        workspace = create_workspace("Lab A", owner["user_id"], db_path=self.db)
        membership = get_membership(workspace["workspace_id"], owner["user_id"], db_path=self.db)
        self.assertEqual(membership.role, "owner")
        self.assertTrue(authorize(owner["user_id"], workspace["workspace_id"], "manage_workspace", db_path=self.db))

    def test_roles_and_permissions(self) -> None:
        owner = create_user("owner", "long-enough-password", db_path=self.db)
        pi = create_user("pi_user", "long-enough-password", db_path=self.db)
        member = create_user("member", "long-enough-password", db_path=self.db)
        viewer = create_user("viewer", "long-enough-password", db_path=self.db)
        workspace = create_workspace("Lab A", owner["user_id"], db_path=self.db)
        wid = workspace["workspace_id"]
        add_member(wid, pi["user_id"], "pi", db_path=self.db)
        add_member(wid, member["user_id"], "member", db_path=self.db)
        add_member(wid, viewer["user_id"], "viewer", db_path=self.db)
        self.assertTrue(authorize(pi["user_id"], wid, "read_all", db_path=self.db))
        self.assertTrue(authorize(pi["user_id"], wid, "copy", db_path=self.db))
        self.assertFalse(authorize(pi["user_id"], wid, "write_workspace", db_path=self.db))
        self.assertTrue(authorize(member["user_id"], wid, "write_own", db_path=self.db))
        self.assertFalse(authorize(member["user_id"], wid, "read_all", db_path=self.db))
        self.assertFalse(authorize(viewer["user_id"], wid, "write_own", db_path=self.db))
        self.assertFalse(authorize(member["user_id"], "ws_missing", "read_workspace", db_path=self.db))

    def test_invalid_role_rejected(self) -> None:
        owner = create_user("owner", "long-enough-password", db_path=self.db)
        workspace = create_workspace("Lab A", owner["user_id"], db_path=self.db)
        with self.assertRaises(TenancyError):
            add_member(workspace["workspace_id"], owner["user_id"], "superuser", db_path=self.db)

    def test_bootstrap_existing_users_is_idempotent(self) -> None:
        first = create_user("first", "long-enough-password", db_path=self.db)
        second = create_user("second", "long-enough-password", db_path=self.db)
        boot = bootstrap_default_workspace(db_path=self.db)
        self.assertTrue(boot["created"])
        self.assertEqual(boot["owner_user_id"], first["user_id"])
        self.assertEqual(get_membership("ws_default", first["user_id"], db_path=self.db).role, "owner")
        self.assertEqual(get_membership("ws_default", second["user_id"], db_path=self.db).role, "member")
        again = bootstrap_default_workspace(db_path=self.db)
        self.assertFalse(again["created"])

    def test_bootstrap_empty_database_creates_pending_local_user(self) -> None:
        boot = bootstrap_default_workspace(db_path=self.db)
        self.assertTrue(boot["created"])
        self.assertIsNone(authenticate("local", "anything", db_path=self.db))

    def test_list_members(self) -> None:
        owner = create_user("owner", "long-enough-password", db_path=self.db)
        workspace = create_workspace("Lab A", owner["user_id"], db_path=self.db)
        members = list_members(workspace["workspace_id"], db_path=self.db)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["role"], "owner")


if __name__ == "__main__":
    unittest.main()
