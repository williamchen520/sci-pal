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

    def query_distribution(self, question: str) -> Dict[str, float]:
        return classify_query(question)

    def prior(self, question: str, paper_id: str, weight: float = 0.1) -> float:
        distribution = self.query_distribution(question)
        domain = self.paper_domain(paper_id)
        return weight * float(distribution.get(domain, 0.0))
