"""Domain lexicon built from PubTator3 entity annotations.

Source: ``services/quality/data/pubtator3_vocab_candidates.tsv`` (1,829 rows:
Gene 724 / Disease 640 / Chemical 450 / Variant 15). Every row carries a
normalized database id; 78 surfaces are ambiguous (same surface, several ids)
and 1,367 terms appear in only one paper, so the lexicon is layered:

* ``curated``  — papers >= 2, canonical length >= 3, not a broad term: authoritative
* ``broad``    — tumor / inflammation / infection ...: never flagged
* ``weak``     — single-paper terms: only evidence that the string was seen

Entity matching is intentionally exact-surface; the FTS fallback in ``guard``
covers terms that only appear in the paper body (PubTator only annotated
titles and abstracts for this corpus).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_LEXICON = (
    Path(__file__).resolve().parent / "data" / "pubtator3_vocab_candidates.tsv"
)
#: Official gene symbols (45k rows) — matched by token, not by the big phrase regex.
HGNC_LEXICON = Path(__file__).resolve().parent / "data" / "hgnc_symbols.tsv"
#: MeSH descriptors (C = disease, D = chemical) — lookup only, never scanned.
MESH_LEXICON = Path(__file__).resolve().parent / "data" / "mesh_descriptors.tsv"

#: Terms that are real entities but too generic to validate against.
BROAD_TERMS = frozenset(
    {
        "tumor", "tumors", "tumour", "tumours", "cancer", "cancers",
        "inflammation", "inflammatory", "infection", "infections",
        "toxicity", "metastasis", "neurodegeneration", "neuroinflammation",
        "lipid", "lipids", "disease", "diseases", "patients", "patient",
        "human", "humans", "mice", "mouse", "cells", "cell",
    }
)

#: Common English words that collide with short entity acronyms ("AS", "AD").
COMMON_WORDS = frozenset(
    {
        "as", "and", "or", "in", "is", "to", "of", "for", "with", "on", "by",
        "at", "an", "the", "be", "are", "was", "were", "it", "its", "this",
        "that", "these", "those", "from", "into", "than", "then", "also",
        "such", "via", "per", "not", "no", "has", "have", "had", "may", "can",
        "more", "most", "other", "than", "only", "both", "same", "within",
        "associated", "respectively", "however", "therefore", "using",
        "failure", "injury", "pain", "shock", "stroke", "growth", "response",
        "expression", "activity", "function", "level", "levels", "effect",
        "effects", "role", "mechanism", "pathway", "signaling", "signalling",
    }
)


#: Greek letters normalised to their latin names.
GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "κ": "kappa", "λ": "lambda", "μ": "mu", "σ": "sigma", "τ": "tau",
}


def normalize_surface(text: str) -> str:
    """Case-fold, unify Greek letters and treat '-', '_', '/' as spaces."""
    value = str(text or "").strip().lower()
    for greek, latin in GREEK.items():
        value = value.replace(greek, latin)
    value = re.sub(r"[-_/]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class Entry:
    type: str
    normalized_id: str
    canonical: str
    aliases: tuple[str, ...] = ()
    mentions: int = 0
    papers: int = 0
    database: str = ""
    source: str = "pubtator"

    @property
    def tier(self) -> str:
        if self.source in {"hgnc", "mesh"}:
            return "curated"  # official vocabularies
        if normalize_surface(self.canonical) in BROAD_TERMS or self.papers >= 100:
            return "broad"
        if self.papers < 2 or len(self.canonical.strip()) < 3:
            return "weak"
        return "curated"


@dataclass
class Lexicon:
    entries: list[Entry] = field(default_factory=list)
    #: normalized surface -> entries (may be several when ambiguous)
    index: dict[str, list[Entry]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None, *, source: str = "pubtator") -> "Lexicon":
        file_path = Path(path) if path else DEFAULT_LEXICON
        entries: list[Entry] = []
        if file_path.exists():
            with file_path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    aliases = tuple(
                        alias.strip()
                        for alias in (row.get("aliases") or "").split(";")
                        if alias.strip()
                    )
                    entries.append(
                        Entry(
                            type=row.get("type", ""),
                            normalized_id=row.get("normalized_id", ""),
                            canonical=row.get("canonical", ""),
                            aliases=aliases,
                            mentions=int(row.get("mentions") or 0),
                            papers=int(row.get("papers") or 0),
                            database=row.get("database", ""),
                            source=source,
                        )
                    )
        lexicon = cls(entries=entries)
        lexicon._build_index()
        return lexicon

    @classmethod
    def load_all(cls) -> "Lexicon":
        """PubTator3 (corpus) + HGNC (official gene symbols) when present."""
        lexicon = cls.load(DEFAULT_LEXICON, source="pubtator")
        if HGNC_LEXICON.exists():
            lexicon.merge(cls.load(HGNC_LEXICON, source="hgnc"))
        if MESH_LEXICON.exists():
            lexicon.merge(cls.load(MESH_LEXICON, source="mesh"))
        return lexicon

    def merge(self, other: "Lexicon") -> "Lexicon":
        existing = {(entry.type, entry.normalized_id) for entry in self.entries}
        for entry in other.entries:
            if (entry.type, entry.normalized_id) not in existing:
                self.entries.append(entry)
        self._build_index()
        return self

    def _build_index(self) -> None:
        self.index = {}
        for entry in self.entries:
            for surface in (entry.canonical, *entry.aliases):
                key = normalize_surface(surface)
                if not key:
                    continue
                bucket = self.index.setdefault(key, [])
                if any(
                    item.type == entry.type and item.normalized_id == entry.normalized_id
                    for item in bucket
                ):
                    continue
                bucket.append(entry)

    def lookup(self, surface: str) -> list[Entry]:
        return self.index.get(normalize_surface(surface), [])

    def preferred(self, surface: str) -> list[Entry]:
        """Resolve multi-source duplicates: a single HGNC row wins over PubTator."""
        entries = self.lookup(surface)
        hgnc = [entry for entry in entries if entry.database == "hgnc"]
        if len(hgnc) == 1:
            return hgnc
        return entries

    def is_curated(self, surface: str) -> bool:
        return any(entry.tier == "curated" for entry in self.lookup(surface))

    def is_ambiguous(self, surface: str) -> bool:
        ids = {(entry.type, entry.normalized_id) for entry in self.lookup(surface)}
        return len(ids) > 1

    def surfaces(self) -> Iterable[str]:
        return self.index.keys()

    def match_surfaces(self) -> Iterable[str]:
        """Only surfaces worth matching: curated/broad tiers, no common words.

        HGNC and MeSH rows are excluded here: tens of thousands of alternatives
        would make the phrase regex slow. Gene symbols are matched by token in
        ``guard``; MeSH is lookup-only (``guard_term`` / disambiguation).
        """
        seen: set[str] = set()
        for entry in self.entries:
            if entry.tier == "weak" or entry.source in {"hgnc", "mesh"}:
                continue
            for surface in (entry.canonical, *entry.aliases):
                text = surface.strip()
                key = normalize_surface(text)
                if len(text) < 2 or not key or key in COMMON_WORDS or key in seen:
                    continue
                seen.add(key)
                yield text
