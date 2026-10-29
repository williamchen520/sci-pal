"""Query-time domain routing and soft paper-domain prior."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Optional

from services.search.domain_taxonomy import classify_query

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


class DomainRouter:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = str(db_path)
        self._paper_domains: Optional[Dict[str, str]] = None

    def _load(self) -> Dict[str, str]:
        if self._paper_domains is not None:
            return self._paper_domains
        conn = sqlite3.connect(self.db_path)
        try:
            self._paper_domains = dict(
                conn.execute("SELECT paper_id, domain_id FROM paper_domains").fetchall()
            )
        except sqlite3.OperationalError:
            self._paper_domains = {}
        finally:
            conn.close()
        return self._paper_domains

    def paper_domain(self, paper_id: str) -> str:
        return self._load().get(paper_id or "", "general")

    def refusal_threshold(self, domain: str) -> float:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT refusal_threshold FROM domain_profiles WHERE domain_id = ?",
                (domain,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            conn.close()
        return float(row[0]) if row and row[0] is not None else 0.35

    def query_distribution(self, question: str) -> Dict[str, float]:
        return classify_query(question)

    def route(
        self,
        question: str,
        paper_ids: list[str] | None = None,
        alpha: float = 0.5,
    ) -> Dict[str, float]:
        query_dist = self.query_distribution(question)
        paper_ids = [pid for pid in (paper_ids or []) if pid]
        if not paper_ids:
            return query_dist
        votes: Dict[str, int] = {}
        for paper_id in paper_ids:
            domain = self.paper_domain(paper_id)
            votes[domain] = votes.get(domain, 0) + 1
        total = sum(votes.values()) or 1
        paper_dist = {domain: count / total for domain, count in votes.items()}
        if set(query_dist) == {"general"}:
            return paper_dist
        merged: Dict[str, float] = {}
        for domain in set(query_dist) | set(paper_dist):
            merged[domain] = alpha * query_dist.get(domain, 0.0) + (1 - alpha) * paper_dist.get(domain, 0.0)
        norm = sum(merged.values()) or 1
        return {domain: value / norm for domain, value in merged.items()}

    def prior(
        self,
        question: str,
        paper_id: str,
        weight: float = 0.1,
        distribution: Dict[str, float] | None = None,
    ) -> float:
        distribution = distribution or self.query_distribution(question)
        domain = self.paper_domain(paper_id)
        return weight * float(distribution.get(domain, 0.0))
