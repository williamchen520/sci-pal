"""Federated retrieval over main and benchmark libraries (P5).

The retriever is deliberately paper/paragraph-level and read-only. It merges
hits by stable work identity (work_id, DOI, then paper_id) and keeps the
per-library provenance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Optional

from services.db.pg_pool import main_read_connection


@dataclass
class FederatedHit:
    scope: str
    paper_id: str
    text: str
    score: float
    title: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    work_id: str = ""
    para_id: str = ""
    provenance: list[dict] = field(default_factory=list)


class FederatedRetriever:
    """Search main and bench libraries, then deduplicate by work identity."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.environ.get("SCIPAL_PG_DSN", "")

    def _pg(self):
        if self.dsn:
            from services.db.pg_pool import pg_connection

            return pg_connection(self.dsn)
        return main_read_connection()

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        scopes: Iterable[str] = ("main", "bench"),
        per_scope_k: int = 20,
    ) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        hits: list[FederatedHit] = []
        for scope in scopes:
            if scope == "main":
                hits.extend(self._search_main(query, per_scope_k))
            elif scope == "bench":
                hits.extend(self._search_bench(query, per_scope_k))
            elif scope == "own":
                # Tenant libraries are introduced in P6; keep the contract now.
                continue
            else:
                raise ValueError(f"unknown library scope: {scope}")
        return self._merge(hits)[:top_k]

    def _search_main(self, query: str, limit: int) -> list[FederatedHit]:
        sql = """
            WITH q AS (SELECT plainto_tsquery('english', %s) AS query)
            SELECT p.para_id, p.paper_id, p.text,
                   ts_rank(p.search_vector, q.query) AS score,
                   pp.title, coalesce(pp.doi, '') AS doi,
                   '' AS pmid, '' AS pmcid,
                   coalesce(ld.work_id, '') AS work_id
            FROM public.paragraphs p
            JOIN public.papers pp ON pp.paper_id = p.paper_id
            LEFT JOIN library_main.paper_documents lpd ON lpd.paper_id = p.paper_id
            LEFT JOIN library_main.documents ld ON ld.document_id = lpd.document_id
            CROSS JOIN q
            WHERE p.search_vector @@ q.query
            ORDER BY score DESC, p.para_id
            LIMIT %s
        """
        return self._run(sql, (query, limit), "main")

    def _search_bench(self, query: str, limit: int) -> list[FederatedHit]:
        sql = """
            WITH q AS (SELECT plainto_tsquery('english', %s) AS query)
            SELECT p.para_id, p.document_id, p.text,
                   ts_rank(to_tsvector('english', p.text), q.query) AS score,
                   coalesce(w.title, '') AS title,
                   coalesce(w.primary_doi, '') AS doi,
                   '' AS pmid, '' AS pmcid,
                   coalesce(d.work_id, '') AS work_id
            FROM library_bench.paragraphs p
            JOIN library_bench.documents d ON d.document_id = p.document_id
            LEFT JOIN catalog.works w ON w.work_id = d.work_id
            CROSS JOIN q
            WHERE to_tsvector('english', p.text) @@ q.query
            ORDER BY score DESC, p.para_id
            LIMIT %s
        """
        return self._run(sql, (query, limit), "bench")

    def _run(self, sql: str, params: tuple, scope: str) -> list[FederatedHit]:
        pg = self._pg()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            pg.close()
        hits = []
        for row in rows:
            hits.append(
                FederatedHit(
                    scope=scope,
                    paper_id=str(row.get("paper_id") or row.get("document_id") or ""),
                    para_id=str(row.get("para_id") or ""),
                    text=str(row.get("text") or ""),
                    score=float(row.get("score") or 0.0),
                    title=str(row.get("title") or ""),
                    doi=str(row.get("doi") or ""),
                    pmid=str(row.get("pmid") or ""),
                    pmcid=str(row.get("pmcid") or ""),
                    work_id=str(row.get("work_id") or ""),
                    provenance=[
                        {
                            "library": scope,
                            "paper_id": str(row.get("paper_id") or row.get("document_id") or ""),
                            "para_id": str(row.get("para_id") or ""),
                        }
                    ],
                )
            )
        return hits

    @staticmethod
    def _key(hit: FederatedHit) -> str:
        if hit.doi:
            return "doi:" + hit.doi.lower()
        if hit.pmid:
            return "pmid:" + hit.pmid
        if hit.pmcid:
            return "pmcid:" + hit.pmcid
        if hit.work_id:
            return "work:" + hit.work_id
        return "paper:" + hit.paper_id

    def _merge(self, hits: list[FederatedHit]) -> list[dict]:
        merged: dict[str, FederatedHit] = {}
        provenance: dict[str, list[dict]] = {}
        for hit in hits:
            key = self._key(hit)
            provenance.setdefault(key, []).extend(hit.provenance)
            current = merged.get(key)
            if current is None or hit.score > current.score:
                merged[key] = hit
        result = []
        for key, hit in merged.items():
            deduped = []
            seen = set()
            for item in provenance[key]:
                marker = (item["library"], item["paper_id"], item["para_id"])
                if marker in seen:
                    continue
                seen.add(marker)
                deduped.append(item)
            result.append(
                {
                    "work_id": hit.work_id,
                    "identity": key,
                    "paper_id": hit.paper_id,
                    "para_id": hit.para_id,
                    "title": hit.title,
                    "doi": hit.doi,
                    "score": hit.score,
                    "text": hit.text,
                    "libraries": sorted({item["library"] for item in deduped}),
                    "provenance": deduped,
                }
            )
        return sorted(result, key=lambda item: (-item["score"], item["paper_id"]))
