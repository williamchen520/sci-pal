"""Schema v2 contract tests (P1, no database required)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SchemaV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = (ROOT / "build_db" / "postgres_schema_v2.sql").read_text(
            encoding="utf-8"
        )

    def test_required_tables(self) -> None:
        for table in (
            "papers",
            "documents",
            "source_nodes",
            "sections",
            "paragraphs",
            "sentences",
            "figures",
            '"tables"',
            "pdf_pages",
            "pdf_blocks",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", self.sql)

    def test_tree_and_source_columns(self) -> None:
        for fragment in (
            "parent_id       TEXT REFERENCES sections(section_id)",
            "parent_node_id  TEXT REFERENCES source_nodes(node_id)",
            "section_id      TEXT REFERENCES sections(section_id)",
            "para_id         TEXT NOT NULL REFERENCES paragraphs(para_id)",
            "source_path     TEXT",
            "native_json     JSONB",
            "pdf_blocks",
            "bbox            TEXT NOT NULL",
        ):
            self.assertIn(fragment, self.sql)

    def test_figure_table_binding_and_coordinates(self) -> None:
        self.assertGreaterEqual(self.sql.count("placement_source"), 2)
        self.assertGreaterEqual(self.sql.count("coordinate_source"), 4)
        self.assertIn("jats-parent", self.sql)
        self.assertIn("pdf-caption", self.sql)
        self.assertIn("xml-unavailable", self.sql)

    def test_sentence_level_fts(self) -> None:
        self.assertIn("search_vector   tsvector GENERATED ALWAYS AS", self.sql)
        self.assertIn("USING GIN (search_vector)", self.sql)
        self.assertIn("to_tsvector('english', coalesce(text, ''))", self.sql)


if __name__ == "__main__":
    unittest.main()
