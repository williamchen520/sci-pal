"""PostgreSQL graph traversal for the P5 paper-graph canary."""

from __future__ import annotations

import os
from collections import deque
from typing import Dict, List, Optional, Set, Tuple


class PGGraphTraverser:
    def __init__(self, dsn: Optional[str] = None, *, connector=None):
        self.dsn = dsn or os.environ.get("SCIPAL_PG_DSN", "")
        self._connector = connector

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.dsn, row_factory=dict_row), True

    def get_neighbors(
        self, paper_ids: List[str], relation: str = "all", direction: str = "both"
    ) -> List[Dict]:
        if not paper_ids:
            return []
        placeholders = ",".join(["%s"] * len(paper_ids))
        rows = []
        pg, close = self._connection()
        try:
            if direction in ("out", "both"):
                q = f"""
                    SELECT c.target_paper_id AS paper_id, c.relation,
                           c.source_paper_id AS via_paper_id, c.confidence,
                           p.title, p.authors, p.year, p.journal
                    FROM cross_paper_index c
                    JOIN papers p ON c.target_paper_id = p.paper_id
                    WHERE c.source_paper_id IN ({placeholders})
                """
                params = list(paper_ids)
                if relation != "all":
                    q += " AND c.relation = %s"
                    params.append(relation)
                rows.extend(pg.execute(q, params).fetchall())
            if direction in ("in", "both"):
                q = f"""
                    SELECT c.source_paper_id AS paper_id, c.relation,
                           c.target_paper_id AS via_paper_id, c.confidence,
                           p.title, p.authors, p.year, p.journal
                    FROM cross_paper_index c
                    JOIN papers p ON c.source_paper_id = p.paper_id
                    WHERE c.target_paper_id IN ({placeholders})
                """
                params = list(paper_ids)
                if relation != "all":
                    q += " AND c.relation = %s"
                    params.append(relation)
                rows.extend(pg.execute(q, params).fetchall())
        finally:
            if close:
                pg.close()

        seeds = set(paper_ids)
        best: Dict[Tuple[str, str], Dict] = {}
        for row in rows:
            value = dict(row)
            key = (value["paper_id"], value["relation"])
            if key not in best or value["confidence"] > best[key]["confidence"]:
                best[key] = value
        result = [value for key, value in best.items() if key[0] not in seeds]
        result.sort(
            key=lambda value: (
                0 if value["relation"] == "similar" else 1,
                -value["confidence"],
            )
        )
        return result

    def traverse(
        self,
        seed_papers: List[str],
        max_hops: int = 2,
        max_total: int = 10,
        relation: str = "all",
    ) -> List[Dict]:
        if not seed_papers:
            return []
        visited: Set[str] = set(seed_papers)
        discovered: List[Dict] = []
        queue: deque = deque((pid, 0) for pid in seed_papers)
        while queue and len(discovered) < max_total:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbor in self.get_neighbors([current], relation=relation):
                if (
                    neighbor["paper_id"] not in visited
                    and len(discovered) < max_total
                ):
                    visited.add(neighbor["paper_id"])
                    neighbor["depth"] = depth + 1
                    discovered.append(neighbor)
                    queue.append((neighbor["paper_id"], depth + 1))
        return discovered
