"""scipal-guard P1: entity vocabulary + corpus landing + abbreviation check.

Three sources, deliberately:

* entity terms  -> PubTator3 lexicon (``services.quality.lexicon``) decides known/unknown
* body terms    -> ``paragraphs_fts`` decides "seen in this corpus" (no new data)
* methods/tech  -> **not judged** (PubTator does not annotate them; flagging = noise)
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from services.quality.lexicon import COMMON_WORDS, Entry, Lexicon, normalize_surface

STOP_ACRONYMS = frozenset(
    {
        "DNA", "RNA", "MRNA", "CDNA", "PCR", "QPCR", "ELISA", "WB", "IHC", "IF",
        "FACS", "SEM", "TEM", "CT", "MRI", "PET", "FDA", "WHO", "NIH", "NCBI",
        "DOI", "PMID", "PMCID", "FIG", "TABLE", "SD", "SE", "CI", "HR", "OR",
        "PBS", "BSA", "DMSO", "EDTA", "SDS", "PAGE", "HPLC", "MS", "NMR",
        "WT", "KO", "NS", "NC", "SI", "AI", "LLM", "API", "URL", "JSON",
    }
)

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "research.db"


def _phrase_pattern(surfaces: Iterable[str]) -> re.Pattern[str]:
    ordered = sorted({s for s in surfaces if s and len(s) >= 2}, key=len, reverse=True)
    alternatives = "|".join(re.escape(s) for s in ordered)
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])", re.IGNORECASE)


_ENTITY_TOKEN = re.compile(
    r"\b(?:[A-Z][A-Z0-9]{1,}[A-Z0-9-]*|[A-Z]{2,}\d+[A-Za-z0-9-]*|IL-\d+|CD\d+|miR-\d+[a-z]?)\b"
)
_DEFINITION = re.compile(r"([A-Za-z][A-Za-z0-9 ,\-]{3,60})\s*\(([A-Z][A-Za-z0-9-]{1,9})\)")


@dataclass
class Issue:
    term: str
    status: str
    detail: str = ""
    preferred: str = ""


@dataclass
class GuardReport:
    issues: list[Issue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def unknown(self) -> int:
        return self.counts.get("unknown", 0)

    @property
    def checked(self) -> int:
        return sum(self.counts.values())

    @property
    def unknown_ratio(self) -> float:
        entity_checked = (
            self.counts.get("known_curated", 0)
            + self.counts.get("ambiguous", 0)
            + self.counts.get("unknown", 0)
        )
        return (self.unknown / entity_checked) if entity_checked else 0.0

    def summary(self) -> dict:
        return {
            "checked": self.checked,
            "unknown": self.unknown,
            "unknown_ratio": round(self.unknown_ratio, 4),
            "counts": dict(self.counts),
            "issues": [issue.__dict__ for issue in self.issues[:50]],
        }


class FtsLanding:
    """Cached ``paragraphs_fts`` membership check (the corpus body source).

    Flask serves requests from a thread pool, so the sqlite connection is kept
    in a ``threading.local`` — a single cached connection raises
    "SQLite objects created in a thread can only be used in that same thread".
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self._cache: dict[str, bool] = {}
        self._local = threading.local()

    def __call__(self, term: str) -> bool:
        key = normalize_surface(term)
        if key in self._cache:
            return self._cache[key]
        hit = False
        try:
            conn = getattr(self._local, "conn", None)
            if conn is None:
                conn = sqlite3.connect(str(self.db_path), timeout=5, check_same_thread=False)
                self._local.conn = conn
            query = '"' + term.replace('"', '""') + '"'
            hit = (
                conn.execute(
                    "SELECT 1 FROM paragraphs_fts WHERE paragraphs_fts MATCH ? LIMIT 1",
                    (query,),
                ).fetchone()
                is not None
            )
        except sqlite3.OperationalError:
            hit = False
        self._cache[key] = hit
        return hit

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


class VocabularyGuard:
    def __init__(
        self,
        lexicon: Lexicon | None = None,
        fts_lookup: Callable[[str], bool] | None = None,
    ) -> None:
        self.lexicon = lexicon or Lexicon.load_all()
        self._fts = fts_lookup
        self._pattern = _phrase_pattern(self.lexicon.match_surfaces())

    def check(self, text: str) -> GuardReport:
        report = GuardReport()
        body = str(text or "")
        self._check_entities(body, report)
        self._check_tokens(body, report)
        self._check_abbreviations(body, report)
        return report

    # ------------------------------------------------------------------
    def _check_entities(self, body: str, report: GuardReport) -> None:
        for match in self._pattern.finditer(body):
            surface = match.group(0)
            if normalize_surface(surface) in COMMON_WORDS:
                continue
            if len(surface.strip()) <= 3 and not surface.strip().isupper():
                continue
            entries: list[Entry] = self.lexicon.preferred(surface)
            if not entries:
                continue
            exact = [
                entry
                for entry in entries
                if normalize_surface(entry.canonical) == normalize_surface(surface)
            ]
            if exact:
                entries = exact
            if len({(entry.type, entry.normalized_id) for entry in entries}) > 1:
                self._add(report, surface, "ambiguous", "多个标准 ID")
                continue
            entry = entries[0]
            if all(item.tier == "broad" for item in entries):
                self._add(report, surface, "known_broad", "泛词，不判")
                continue
            if exact:
                # the canonical spelling itself is authoritative, even if the
                # surface was only annotated in one paper
                self._add(report, surface, "known_curated", entry.normalized_id)
                continue
            tier = entry.tier
            if tier == "broad":
                self._add(report, surface, "known_broad", "泛词，不判")
            elif tier == "weak":
                self._add(report, surface, "known_weak", "仅 1 篇论文出现")
            else:
                self._add(report, surface, "known_curated", entry.normalized_id)

    def _check_tokens(self, body: str, report: GuardReport) -> None:
        """Gene-symbol tokens: HGNC/PubTator hit → known; else FTS → corpus/unknown."""
        reported = {issue.term.upper() for issue in report.issues}
        known_surfaces = {normalize_surface(surface) for surface in self.lexicon.match_surfaces()}
        for match in _ENTITY_TOKEN.finditer(body):
            token = match.group(0)
            upper = token.upper()
            if (
                upper in STOP_ACRONYMS
                or upper in reported
                or normalize_surface(token) in COMMON_WORDS
            ):
                continue
            entries = self.lexicon.preferred(token)
            if entries:
                ids = {(entry.type, entry.normalized_id) for entry in entries}
                if len(ids) > 1:
                    self._add(report, token, "ambiguous", "多个标准 ID")
                else:
                    self._add(report, token, "known_curated", entries[0].normalized_id)
                reported.add(upper)
                continue
            if normalize_surface(token) in known_surfaces:
                continue
            landed = bool(self._fts and self._fts(token))
            if landed:
                self._add(report, token, "corpus", "正文出现过（方法/技术类不判）")
            else:
                self._add(report, token, "unknown", "词表与正文均未见")
            reported.add(upper)

    def _check_abbreviations(self, body: str, report: GuardReport) -> None:
        defined = {match.group(2).upper() for match in _DEFINITION.finditer(body)}
        reported = {issue.term.upper() for issue in report.issues}
        seen: set[str] = set()
        for match in _ENTITY_TOKEN.finditer(body):
            token = match.group(0)
            if len(token) < 2 or len(token) > 8 or token.upper() in STOP_ACRONYMS:
                continue
            upper = token.upper()
            if not token.isupper() or upper in defined or upper in seen or upper in reported:
                continue
            seen.add(upper)
            entries = self.lexicon.preferred(token)
            if entries or (self._fts and self._fts(token)):
                continue
            self._add(report, token, "undefined_abbrev", "缩写未定义")

    @staticmethod
    def _add(report: GuardReport, term: str, status: str, detail: str = "",
             preferred: str = "") -> None:
        report.counts[status] = report.counts.get(status, 0) + 1
        report.issues.append(Issue(term=term, status=status, detail=detail, preferred=preferred))
