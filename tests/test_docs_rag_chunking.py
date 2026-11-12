"""Tests for independent docs RAG chunking."""

from __future__ import annotations

import unittest

from docs_rag.chunking import chunk_markdown, token_count


class DocsChunkingTests(unittest.TestCase):
    def test_heading_sections_become_chunks(self) -> None:
        chunks = chunk_markdown("# Intro\n\nAlpha.\n\n## Detail\n\nBeta.")
        self.assertEqual([chunk.heading for chunk in chunks], ["Intro", "Intro > Detail"])
        self.assertEqual([chunk.text for chunk in chunks], ["Alpha.", "Beta."])

    def test_code_fence_heading_is_not_a_section(self) -> None:
        chunks = chunk_markdown("# A\n\n```\n# not a heading\n```\n\ntext")
        self.assertEqual(len(chunks), 1)
        self.assertIn("# not a heading", chunks[0].text)

    def test_oversized_section_splits_with_no_empty_chunks(self) -> None:
        chunks = chunk_markdown("# A\n\n" + ("句子。" * 1000), max_chars=300)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))

    def test_token_count_handles_chinese_and_ascii(self) -> None:
        self.assertEqual(token_count("独立建库 core/rebuild"), 6)


if __name__ == "__main__":
    unittest.main()
