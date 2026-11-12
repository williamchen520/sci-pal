"""Tests for public evaluation-set loaders."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eval.public_sets import load_qasper, load_scifact


class PublicSetLoaderTests(unittest.TestCase):
    def test_scifact_beir_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "corpus.jsonl").write_text(
                json.dumps(
                    {
                        "_id": "1",
                        "title": "A paper",
                        "text": "Alpha one. Beta two.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "queries.jsonl").write_text(
                json.dumps({"_id": "q1", "text": "Alpha?"}) + "\n",
                encoding="utf-8",
            )
            (root / "qrels.tsv").write_text("query-id\tcorpus-id\tscore\nq1\t1\t1\n", encoding="utf-8")

            dataset = load_scifact(
                root / "corpus.jsonl",
                root / "queries.jsonl",
                root / "qrels.tsv",
            )

        self.assertEqual(dataset.evidence_level, "document")
        self.assertEqual([p.paper_id for p in dataset.papers], ["scifact_1"])
        self.assertEqual(len(dataset.sentences), 2)
        self.assertEqual(
            [s.sentence_id for s in dataset.sentences],
            ["scifact_1_s0000", "scifact_1_s0001"],
        )
        self.assertEqual(dataset.claims[0].gold_paper_ids, ("scifact_1",))
        self.assertEqual(dataset.claims[0].gold_sentence_ids, ())

    def test_qasper_loader_keeps_evidence_level_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qasper.json"
            path.write_text(
                json.dumps(
                    {
                        "p1": {
                            "title": "A paper",
                            "full_text": [
                                {
                                    "section_name": "Intro",
                                    "paragraphs": ["Alpha one. Beta two."],
                                }
                            ],
                            "qas": [
                                {
                                    "question_id": "q1",
                                    "question": "Alpha?",
                                    "answers": [],
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            dataset = load_qasper(path)

        self.assertEqual(dataset.evidence_level, "paragraph")
        self.assertEqual(dataset.papers[0].paper_id, "qasper_p1")
        self.assertEqual(len(dataset.sentences), 2)
        self.assertEqual(dataset.claims[0].evidence_level, "paragraph")
        self.assertEqual(dataset.claims[0].gold_paper_ids, ("qasper_p1",))


if __name__ == "__main__":
    unittest.main()
