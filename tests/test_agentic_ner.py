"""NER is expensive (~87 s model load); it must stay off the common path."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.search import agentic_search as agentic


class EntityExtractionTests(unittest.TestCase):
    def test_regex_gene_skips_ner(self) -> None:
        calls = []
        original = agentic._extract_genes_with_ner
        agentic._extract_genes_with_ner = lambda text: calls.append(text) or []
        try:
            entities = agentic.extract_key_entities("TLR4 sepsis")
        finally:
            agentic._extract_genes_with_ner = original
        self.assertEqual(calls, [])
        self.assertIn("TLR4", entities)

    def test_env_flag_disables_ner(self) -> None:
        calls = []
        original = agentic._extract_genes_with_ner
        agentic._extract_genes_with_ner = lambda text: calls.append(text) or []
        try:
            with patch.dict(os.environ, {"SCIPAL_DISABLE_NER": "1"}):
                agentic.extract_key_entities("interferon signalling")
        finally:
            agentic._extract_genes_with_ner = original
        self.assertEqual(calls, [])

    def test_ner_runs_when_regex_finds_nothing(self) -> None:
        calls = []
        original = agentic._extract_genes_with_ner
        agentic._extract_genes_with_ner = lambda text: calls.append(text) or ["IL6"]
        try:
            with patch.dict(os.environ, {"SCIPAL_DISABLE_NER": ""}):
                entities = agentic.extract_key_entities("interferon signalling")
        finally:
            agentic._extract_genes_with_ner = original
        self.assertEqual(len(calls), 1)
        self.assertIn("IL6", entities)


if __name__ == "__main__":
    unittest.main()
