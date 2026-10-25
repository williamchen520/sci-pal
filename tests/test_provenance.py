"""Tests for record identity, fingerprints and quote anchors."""

from __future__ import annotations

import unittest

from services.records.provenance import (
    anchor_matches,
    canonical_identifier,
    make_anchor,
    quote_hash,
    result_fingerprint,
    stable_record_id,
)


class StableRecordIdTests(unittest.TestCase):
    def test_strong_identifier_priority(self) -> None:
        record = {"doi": "10.1038/nature14539", "pmid": "28344011"}
        self.assertEqual(
            stable_record_id(record), "paper:doi:10.1038/nature14539"
        )

    def test_doi_canonicalized(self) -> None:
        left = stable_record_id({"doi": "https://doi.org/10.1038/NATURE14539"})
        right = stable_record_id({"doi": "DOI: 10.1038/nature14539."})
        self.assertEqual(left, right)

    def test_namespaces_per_identifier(self) -> None:
        self.assertEqual(stable_record_id({"pmid": 28344011}), "paper:pmid:28344011")
        self.assertEqual(stable_record_id({"pmcid": "pmc123"}), "paper:pmcid:PMC123")
        self.assertEqual(
            stable_record_id({"arxiv_id": "1706.03762v5"}), "paper:arxiv:1706.03762"
        )

    def test_entity_type_override(self) -> None:
        self.assertTrue(
            stable_record_id({"doi": "10.1/x"}, entity_type="preprint").startswith("preprint:doi:")
        )

    def test_fallback_is_stable_across_formatting(self) -> None:
        a = stable_record_id({"title": "Deep Learning: A Review.", "year": 2015, "authors": ["LeCun, Yann", "Bengio, Yoshua"]})
        b = stable_record_id({"title": "deep learning a review", "year": "2015-05-28", "authors": ["LeCun, Yann"]})
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("paper:sha256:"))

    def test_fallback_changes_with_content(self) -> None:
        a = stable_record_id({"title": "Deep Learning", "year": 2015, "authors": ["LeCun"]})
        b = stable_record_id({"title": "Deep Learning", "year": 2016, "authors": ["LeCun"]})
        self.assertNotEqual(a, b)

    def test_missing_everything_is_still_deterministic(self) -> None:
        self.assertEqual(stable_record_id({}), stable_record_id({}))

    def test_author_mapping_form(self) -> None:
        a = stable_record_id({"title": "T", "year": 2020, "authors": [{"family": "Smith"}]})
        b = stable_record_id({"title": "T", "year": 2020, "authors": ["Smith"]})
        self.assertEqual(a, b)


class FingerprintTests(unittest.TestCase):
    def test_prefix_and_determinism(self) -> None:
        ids = ["paper:doi:10.1/a", "paper:doi:10.1/b"]
        self.assertTrue(result_fingerprint(ids).startswith("sha256:"))
        self.assertEqual(result_fingerprint(ids), result_fingerprint(ids))

    def test_order_matters(self) -> None:
        self.assertNotEqual(
            result_fingerprint(["a", "b"]), result_fingerprint(["b", "a"])
        )

    def test_empty(self) -> None:
        self.assertTrue(result_fingerprint([]).startswith("sha256:"))


class QuoteAnchorTests(unittest.TestCase):
    def test_quote_hash_ignores_layout_noise(self) -> None:
        a = quote_hash("Deep learning allows computational models...")
        b = quote_hash("Deep  learning, allows computational models")
        self.assertEqual(a, b)

    def test_quote_hash_detects_content_change(self) -> None:
        self.assertNotEqual(quote_hash("mortality fell by 20%"), quote_hash("mortality fell by 12%"))

    def test_quote_hash_handles_cjk(self) -> None:
        self.assertTrue(quote_hash("深 度 学 习").startswith("sha256:"))
        self.assertEqual(quote_hash("深度学习"), quote_hash("深度学习"))

    def test_anchor_schema(self) -> None:
        anchor = make_anchor(42, "some text")
        self.assertEqual(anchor["schema_version"], "1")
        self.assertEqual(anchor["para_id"], 42)
        self.assertTrue(anchor["quote_hash"].startswith("sha256:"))

    def test_anchor_matches_reflowed_text(self) -> None:
        anchor = make_anchor("p1", "The model was trained on 1.2M papers.")
        self.assertTrue(anchor_matches(anchor, "the model was trained on 1 2M papers"))

    def test_anchor_rejects_changed_text(self) -> None:
        anchor = make_anchor("p1", "The model was trained on 1.2M papers.")
        self.assertFalse(anchor_matches(anchor, "The model was trained on 12M papers."))

    def test_anchor_without_hash_never_matches(self) -> None:
        self.assertFalse(anchor_matches({}, "anything"))


class CanonicalIdentifierTests(unittest.TestCase):
    def test_identifiers(self) -> None:
        self.assertEqual(canonical_identifier("doi", "DOI:10.1038/NATURE14539"), "10.1038/nature14539")
        self.assertEqual(canonical_identifier("pmcid", "pmc123"), "PMC123")
        self.assertEqual(
            canonical_identifier("arxiv_id", "https://arxiv.org/pdf/1706.03762v5.pdf"),
            "1706.03762",
        )


if __name__ == "__main__":
    unittest.main()
