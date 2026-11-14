"""Paper code-link tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import code_links


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=()):
        return _Cursor(self.rows)

    def close(self):
        return None


class CodeLinkTests(unittest.TestCase):
    def test_extract_and_dedupe(self) -> None:
        rows = [
            {"para_id": "p1", "text": "Code: https://github.com/a/b. Next."},
            {"para_id": "p2", "text": "See https://github.com/a/b and https://zenodo.org/x"},
        ]
        with mock.patch.object(code_links, "corpus_connection", return_value=_Conn(rows)):
            links = code_links.extract_candidates("paper")
        self.assertEqual({link["url"] for link in links}, {
            "https://github.com/a/b",
            "https://zenodo.org/x",
        })
        self.assertEqual(links[0]["status"], "candidate")

    def test_manual_rejects_non_repo_host(self) -> None:
        with self.assertRaises(ValueError):
            code_links.manual_link("paper", "https://example.com/repo")

    def test_resolve_github_metadata(self) -> None:
        payloads = [
            {"license": {"spdx_id": "MIT"}, "default_branch": "main"},
            {"sha": "abc123"},
        ]
        with mock.patch.object(code_links, "_fetch_json", side_effect=payloads):
            meta = code_links.resolve_metadata("https://github.com/a/b")
        self.assertEqual(meta["license"], "MIT")
        self.assertEqual(meta["commit_sha"], "abc123")
        self.assertEqual(meta["status"], "validated")

    def test_resolve_zenodo_metadata(self) -> None:
        with mock.patch.object(
            code_links, "_fetch_json", return_value={"metadata": {"license": {"id": "GPL-3.0"}}}
        ):
            meta = code_links.resolve_metadata("https://doi.org/10.5281/zenodo.123")
        self.assertEqual(meta["repo_type"], "zenodo")
        self.assertEqual(meta["license"], "GPL-3.0")

    def test_manual_link(self) -> None:
        with mock.patch.object(code_links, "_upsert", return_value=1):
            link = code_links.manual_link(
                "paper", "https://github.com/a/b", license_value="MIT", status="validated"
            )
        self.assertEqual(link["repo_type"], "github")
        self.assertEqual(link["status"], "validated")
        self.assertEqual(link["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
