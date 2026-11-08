"""PostgreSQL FTS adapters for paragraphs and section summaries.

These are shadow-read candidates: they do not change production routing yet.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import List, Optional

from services.search.fts_query_builder import _extract_keywords


@dataclass
class ParagraphHit:
    para_id: str
    paper_id: str
    section_level1: Optional[str]
    section_level2: Optional[str]
    text: str
    rank: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SentenceHit:
    sentence_id: str
    para_id: str
    paper_id: str
    text: str
    rank: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SummaryHit:
    summary_id: str
    paper_id: str
    section_id: Optional[str]
    level: Optional[int]
    title: Optional[str]
    text: str
    rank: float

    def as_dict(self) -> dict:
        return asdict(self)


class _BasePG:
    def __init__(self, dsn: Optional[str] = None, *, connector=None, ranker: str = "rank_cd"):
        self.dsn = dsn
        self._connector = connector
        if ranker not in ("rank", "rank_cd"):
            raise ValueError("ranker must be rank or rank_cd")
        self.ranker = ranker

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        from services.db.pg_pool import main_read_connection, pg_connection

        return (pg_connection(self.dsn) if self.dsn else main_read_connection()), True

    def _lexemes(self, pg, terms: list[str], source: str) -> list[str]:
        """Map query words to PG lexemes and rank them by rarity."""
        try:
            rows = pg.execute(
                "SELECT t.term, l.lexeme FROM unnest(%s::text[]) AS t(term), "
                "LATERAL unnest(to_tsvector('english', t.term)) AS l(lexeme)",
                (terms,),
            ).fetchall()
        except Exception:  # noqa: BLE001 - optional stats path
            return terms
        by_term: dict[str, list[str]] = {}
        try:
            for row in rows:
                by_term.setdefault(row["term"], []).append(row["lexeme"])
        except Exception:  # noqa: BLE001 - fake/absent stats rows
            return terms
        lexemes = []
        for term in terms:
            lexemes.extend(by_term.get(term, []))
        return list(dict.fromkeys(lexemes)) or terms

    def _query(
        self,
        query: str,
        match: str,
        term_limit: int,
        *,
        pg=None,
        source: str = "paragraphs",
    ) -> str:
        limit = max(1, min(term_limit, 12))
        terms = _extract_keywords(query)
        if not terms:
            return ""
        if pg is None:
            pg, close = self._connection()
            try:
                return self._query(query, match, term_limit, pg=pg, source=source)
            finally:
                if close:
                    pg.close()
        lexemes = self._lexemes(pg, terms, source)
        try:
            rows = pg.execute(
                "SELECT word, nentry FROM fts_term_stats WHERE source = %s AND word = ANY(%s)",
                (source, lexemes),
            ).fetchall()
        except Exception:  # noqa: BLE001 - stats table may not exist yet
            return (" | " if match == "any" else " & ").join(lexemes)
        try:
            rarity = {row["word"]: int(row["nentry"]) for row in rows}
        except Exception:  # noqa: BLE001 - fake/absent stats rows
            return (" | " if match == "any" else " & ").join(lexemes)
        ranked = sorted(
            enumerate(lexemes),
            key=lambda item: (rarity.get(item[1], 10**12), item[0]),
        )
        selected = [word for _, word in ranked[:limit]]
        return (" | " if match == "any" else " & ").join(selected or lexemes)

    @property
    def _rank_expr(self) -> str:
        return "ts_rank_cd" if self.ranker == "rank_cd" else "ts_rank"


class PGParagraphFTS(_BasePG):
    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        paper_id: str = "",
        section_level1: str = "",
        match: str = "any",
        term_limit: int = 12,
    ) -> List[ParagraphHit]:
        query = (query or "").strip()
        if not query:
            return []
        if match not in ("any", "all"):
            raise ValueError("match must be any or all")
        ts_query = self._query(query, match, term_limit)
        if not ts_query:
            return []
        where = "p.search_vector @@ q.query"
        params: list = [ts_query]
        if paper_id:
            where += " AND p.paper_id = %s"
            params.append(paper_id)
        if section_level1:
            where += " AND p.section_level1 = %s"
            params.append(section_level1)
        params.append(top_k)
        sql = f"""
            WITH q AS (SELECT to_tsquery('english', %s) AS query)
            SELECT p.para_id, p.paper_id, p.section_level1, p.section_level2,
                   p.text, {self._rank_expr}(p.search_vector, q.query) AS rank
            FROM paragraphs p
            JOIN papers pp ON pp.paper_id = p.paper_id AND pp.duplicate_of IS NULL
            CROSS JOIN q
            WHERE {where}
            ORDER BY rank DESC, p.para_id
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [ParagraphHit(**row) for row in rows]

    def recall(
        self,
        query: str,
        *,
        top_n: int = 200,
        paper_id: str = "",
        section_level1: str = "",
        match: str = "any",
        term_limit: int = 6,
    ) -> List[ParagraphHit]:
        """Cheap GIN recall without database-side ranking."""
        query = (query or "").strip()
        if not query:
            return []
        if match not in ("any", "all"):
            raise ValueError("match must be any or all")
        ts_query = self._query(query, match, term_limit)
        if not ts_query:
            return []
        where = "p.search_vector @@ q.query"
        params: list = [ts_query]
        if paper_id:
            where += " AND p.paper_id = %s"
            params.append(paper_id)
        if section_level1:
            where += " AND p.section_level1 = %s"
            params.append(section_level1)
        params.append(top_n)
        sql = f"""
            WITH q AS (SELECT to_tsquery('english', %s) AS query)
            SELECT p.para_id, p.paper_id, p.section_level1, p.section_level2,
                   p.text, 0.0::float8 AS rank
            FROM paragraphs p
            JOIN papers pp ON pp.paper_id = p.paper_id AND pp.duplicate_of IS NULL
            CROSS JOIN q
            WHERE {where}
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [ParagraphHit(**row) for row in rows]


class PGSummaryFTS(_BasePG):
    def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        paper_id: str = "",
        match: str = "any",
        term_limit: int = 8,
    ) -> List[SummaryHit]:
        query = (query or "").strip()
        if not query:
            return []
        if match not in ("any", "all"):
            raise ValueError("match must be any or all")
        ts_query = self._query(query, match, term_limit)
        if not ts_query:
            return []
        where = "s.search_vector @@ q.query"
        params: list = [ts_query]
        if paper_id:
            where += " AND s.paper_id = %s"
            params.append(paper_id)
        params.append(top_k)
        sql = f"""
            WITH q AS (SELECT to_tsquery('english', %s) AS query)
            SELECT s.summary_id, s.paper_id, s.section_id, s.level, s.title,
                   s.text, {self._rank_expr}(s.search_vector, q.query) AS rank
            FROM summaries s
            JOIN papers pp ON pp.paper_id = s.paper_id AND pp.duplicate_of IS NULL
            CROSS JOIN q
            WHERE {where}
            ORDER BY rank DESC, s.summary_id
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [SummaryHit(**row) for row in rows]

    def recall(
        self,
        query: str,
        *,
        top_n: int = 200,
        paper_id: str = "",
        match: str = "any",
        term_limit: int = 6,
    ) -> List[SummaryHit]:
        query = (query or "").strip()
        if not query:
            return []
        if match not in ("any", "all"):
            raise ValueError("match must be any or all")
        ts_query = self._query(query, match, term_limit)
        if not ts_query:
            return []
        where = "s.search_vector @@ q.query"
        params: list = [ts_query]
        if paper_id:
            where += " AND s.paper_id = %s"
            params.append(paper_id)
        params.append(top_n)
        sql = f"""
            WITH q AS (SELECT to_tsquery('english', %s) AS query)
            SELECT s.summary_id, s.paper_id, s.section_id, s.level, s.title,
                   s.text, 0.0::float8 AS rank
            FROM summaries s
            JOIN papers pp ON pp.paper_id = s.paper_id AND pp.duplicate_of IS NULL
            CROSS JOIN q
            WHERE {where}
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [SummaryHit(**row) for row in rows]

class ParadeDBParagraphFTS:
    """BM25 paragraph recall through ParadeDB pg_search.

    This adapter is deliberately separate from :class:`PGParagraphFTS`:
    ``@@@`` + ``pdb.score`` are ParadeDB syntax, not native PostgreSQL FTS.
    """

    def __init__(self, dsn: Optional[str] = None, *, connector=None):
        self.dsn = dsn or os.environ.get("SCIPAL_PARADEDB_DSN") or os.environ.get(
            "SCIPAL_PG_DSN", ""
        )
        self._connector = connector

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        from services.db.pg_pool import main_read_connection, pg_connection

        return (pg_connection(self.dsn) if self.dsn else main_read_connection()), True

    @staticmethod
    def _bm25_query(query: str, match: str, term_limit: int) -> str:
        import re

        limit = max(1, min(term_limit, 12))
        safe = lambda value: bool(re.fullmatch(r"[A-Za-z0-9_]+", value))  # noqa: E731
        phrases = []
        for raw in re.findall(r'"([^"]{2,80})"', query):
            words = [part for part in re.findall(r"[A-Za-z0-9_]+", raw) if safe(part)]
            if words:
                phrases.append('"' + " ".join(words) + '"')
        terms = [
            term for term in (_extract_keywords(query) or []) if safe(term)
        ]
        parts = list(dict.fromkeys(phrases + terms))[:limit]
        if not parts:
            return ""
        joiner = " AND " if match == "all" else " OR "
        return joiner.join(parts)

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        paper_id: str = "",
        section_level1: str = "",
        match: str = "any",
        term_limit: int = 12,
    ) -> List[ParagraphHit]:
        query = (query or "").strip()
        if not query:
            return []
        if match not in ("any", "all"):
            raise ValueError("match must be any or all")
        bm25_query = self._bm25_query(query, match, term_limit)
        if not bm25_query:
            return []
        where = "p.text @@@ %s"
        params: list = [bm25_query]
        if paper_id:
            where += " AND p.paper_id = %s"
            params.append(paper_id)
        if section_level1:
            where += " AND p.section_level1 = %s"
            params.append(section_level1)
        params.append(top_k)
        sql = f"""
            SELECT p.para_id, p.paper_id, p.section_level1, p.section_level2,
                   p.text, pdb.score(p.para_id) AS rank
            FROM paragraphs p
            WHERE {where}
            ORDER BY rank DESC, p.para_id
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [ParagraphHit(**row) for row in rows]

class ParadeDBSummaryFTS(ParadeDBParagraphFTS):
    """BM25 section-summary recall through ParadeDB."""

    def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        paper_id: str = "",
        match: str = "any",
        term_limit: int = 8,
    ) -> List[SummaryHit]:
        query = (query or "").strip()
        if not query:
            return []
        bm25_query = self._bm25_query(query, match, term_limit)
        if not bm25_query:
            return []
        where = "(s.title @@@ %s OR s.text @@@ %s)"
        params: list = [bm25_query, bm25_query]
        if paper_id:
            where += " AND s.paper_id = %s"
            params.append(paper_id)
        params.append(top_k)
        sql = f"""
            SELECT s.summary_id, s.paper_id, s.section_id, s.level,
                   s.title, s.text, pdb.score(s.summary_id) AS rank
            FROM summaries s
            WHERE {where}
            ORDER BY rank DESC, s.summary_id
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [SummaryHit(**row) for row in rows]


class ParadeDBSentenceFTS(ParadeDBParagraphFTS):
    """BM25 sentence recall through ParadeDB.

    Used for highlight selection and sentence-level verification, not as a
    replacement for paragraph retrieval.
    """

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        paper_id: str = "",
        para_id: str = "",
        match: str = "any",
        term_limit: int = 12,
    ) -> List[SentenceHit]:
        query = (query or "").strip()
        if not query:
            return []
        bm25_query = self._bm25_query(query, match, term_limit)
        if not bm25_query:
            return []
        where = "s.text @@@ %s"
        params: list = [bm25_query]
        if paper_id:
            where += " AND s.paper_id = %s"
            params.append(paper_id)
        if para_id:
            where += " AND s.para_id = %s"
            params.append(para_id)
        params.append(top_k)
        sql = f"""
            SELECT s.sentence_id, s.para_id, s.paper_id, s.text,
                   pdb.score(s.sentence_id) AS rank
            FROM sentences s
            WHERE {where}
            ORDER BY rank DESC, s.sentence_id
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [SentenceHit(**row) for row in rows]
