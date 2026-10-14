"""
Graph traversal for paper discovery.
V23.1 - T3 Graph Traversal

Given a set of seed papers (from vector retrieval), expand to related papers
via CITES and SIMILAR edges stored in cross_paper_index. This enables
"find papers related to this one" and multi-hop literature discovery.

Edges:
  - cites:    directed, A cites B (source_paper_id -> target_paper_id)
  - similar:  undirected (stored both directions), cosine > threshold
"""
import sqlite3
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"


class GraphTraverser:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DB_PATH)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    # Core: neighbor lookup
    # ------------------------------------------------------------------
    def get_neighbors(self, paper_ids: List[str],
                      relation: str = "all",
                      direction: str = "both") -> List[Dict]:
        """
        Get direct neighbors of the given papers.

        Args:
            paper_ids: seed paper IDs
            relation: 'cites' | 'similar' | 'all'
            direction: 'out' (cites), 'in' (cited_by), 'both'

        Returns:
            List of {paper_id, title, authors, year, journal,
                     relation, via_paper_id, confidence}
        """
        if not paper_ids:
            return []

        placeholders = ",".join("?" * len(paper_ids))
        rows = []

        # Outgoing edges: seed -> neighbor
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
                q += " AND c.relation = ?"
                params.append(relation)
            rows.extend(self.conn.execute(q, params).fetchall())

        # Incoming edges: neighbor -> seed (only meaningful for cites)
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
                q += " AND c.relation = ?"
                params.append(relation)
            rows.extend(self.conn.execute(q, params).fetchall())

        # Deduplicate by (paper_id, relation), keep highest confidence
        best: Dict[Tuple[str, str], Dict] = {}
        for r in rows:
            key = (r["paper_id"], r["relation"])
            if key not in best or r["confidence"] > best[key]["confidence"]:
                best[key] = dict(r)

        # Exclude seeds themselves
        result = [v for k, v in best.items() if k[0] not in set(paper_ids)]
        # Sort: similar first (higher confidence usually), then cites
        result.sort(key=lambda x: (0 if x["relation"] == "similar" else 1,
                                    -x["confidence"]))
        return result

    # ------------------------------------------------------------------
    # Expand: from seed papers, get top related papers
    # ------------------------------------------------------------------
    def expand(self, seed_papers: List[str],
               max_neighbors: int = 5,
               relation: str = "all") -> List[Dict]:
        """
        One-hop expansion from seed papers to related papers.

        This is the main API used by UnifiedRetriever: after vector retrieval
        finds seed papers, expand via graph to find semantically related papers
        that vector search might have missed.
        """
        neighbors = self.get_neighbors(seed_papers, relation=relation)
        return neighbors[:max_neighbors]

    # ------------------------------------------------------------------
    # BFS multi-hop traversal
    # ------------------------------------------------------------------
    def traverse(self, seed_papers: List[str],
                 max_hops: int = 2,
                 max_total: int = 10,
                 relation: str = "all") -> List[Dict]:
        """
        BFS traversal from seed papers, up to max_hops deep.

        Returns a list of discovered papers (excluding seeds), each with
        a 'depth' field indicating how many hops from the nearest seed.
        """
        if not seed_papers:
            return []

        visited: Set[str] = set(seed_papers)
        discovered: List[Dict] = []
        queue: deque = deque([(pid, 0) for pid in seed_papers])

        while queue and len(discovered) < max_total:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue

            neighbors = self.get_neighbors([current], relation=relation)
            for nb in neighbors:
                if nb["paper_id"] not in visited and len(discovered) < max_total:
                    visited.add(nb["paper_id"])
                    nb["depth"] = depth + 1
                    discovered.append(nb)
                    queue.append((nb["paper_id"], depth + 1))

        return discovered

    # ------------------------------------------------------------------
    # Paper detail batch lookup
    # ------------------------------------------------------------------
    def get_paper_details(self, paper_ids: List[str]) -> List[Dict]:
        """Get title/authors/year/journal for a list of paper IDs."""
        if not paper_ids:
            return []
        placeholders = ",".join("?" * len(paper_ids))
        rows = self.conn.execute(
            f"SELECT paper_id, title, authors, year, journal, doi, "
            f"total_paragraphs, total_figures FROM papers "
            f"WHERE paper_id IN ({placeholders})",
            paper_ids
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Graph statistics
    # ------------------------------------------------------------------
    def stats(self) -> Dict:
        """Return graph statistics."""
        n_papers = self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        n_cites = self.conn.execute(
            "SELECT COUNT(*) FROM cross_paper_index WHERE relation='cites'"
        ).fetchone()[0]
        n_similar = self.conn.execute(
            "SELECT COUNT(*) FROM cross_paper_index WHERE relation='similar'"
        ).fetchone()[0]

        # Top cited papers (in-degree)
        top_cited = self.conn.execute("""
            SELECT p.title, p.year, COUNT(*) as cnt
            FROM cross_paper_index c
            JOIN papers p ON c.target_paper_id = p.paper_id
            WHERE c.relation = 'cites'
            GROUP BY c.target_paper_id
            ORDER BY cnt DESC
            LIMIT 5
        """).fetchall()

        # Connected components (BFS)
        adj: Dict[str, Set[str]] = {}
        for src, tgt in self.conn.execute(
                "SELECT source_paper_id, target_paper_id FROM cross_paper_index"):
            adj.setdefault(src, set()).add(tgt)
            adj.setdefault(tgt, set()).add(src)

        visited = set()
        components = 0
        largest = 0
        for node in adj:
            if node not in visited:
                components += 1
                size = 0
                stack = [node]
                while stack:
                    n = stack.pop()
                    if n in visited:
                        continue
                    visited.add(n)
                    size += 1
                    stack.extend(adj.get(n, set()) - visited)
                largest = max(largest, size)

        isolated = n_papers - len(visited)

        return {
            "papers": n_papers,
            "cites_edges": n_cites,
            "similar_edges": n_similar,
            "connected_components": components,
            "largest_component": largest,
            "isolated_papers": isolated,
            "top_cited": [dict(r) for r in top_cited],
        }

    def close(self):
        self.conn.close()


# ======================================================================
# Self-test
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🕸️  Graph Traverser Test (V23.1)")
    print("=" * 60)

    gt = GraphTraverser()

    # Graph stats
    print("\n── Graph statistics ──")
    s = gt.stats()
    print(f"  Papers: {s['papers']}")
    print(f"  CITES edges: {s['cites_edges']}")
    print(f"  SIMILAR edges: {s['similar_edges']}")
    print(f"  Connected components: {s['connected_components']}")
    print(f"  Largest component: {s['largest_component']}")
    print(f"  Isolated papers: {s['isolated_papers']}")
    print(f"  Top cited:")
    for p in s["top_cited"]:
        print(f"    [{p['cnt']}x] {p['title'][:60]} ({p['year']})")

    # Pick a paper that has neighbors
    print("\n── Find a paper with graph connections ──")
    row = gt.conn.execute("""
        SELECT source_paper_id FROM cross_paper_index LIMIT 1
    """).fetchone()
    if row:
        seed_id = row["source_paper_id"]
        seed_detail = gt.get_paper_details([seed_id])
        if seed_detail:
            print(f"  Seed: {seed_detail[0]['title'][:60]}")

            # One-hop expansion
            print("\n── One-hop expansion (top 5) ──")
            neighbors = gt.expand([seed_id], max_neighbors=5)
            for i, nb in enumerate(neighbors, 1):
                print(f"  [{i}] ({nb['relation']}, conf={nb['confidence']:.2f}) "
                      f"{nb['title'][:55]} ({nb.get('year') or '?'})")

            # Multi-hop BFS
            print("\n── Multi-hop BFS (2 hops, max 8) ──")
            discovered = gt.traverse([seed_id], max_hops=2, max_total=8)
            for i, d in enumerate(discovered, 1):
                print(f"  [{i}] depth={d['depth']} ({d['relation']}) "
                      f"{d['title'][:50]} ({d.get('year') or '?'})")
    else:
        print("  No graph edges found — run build_paper_graph.py --apply first.")

    gt.close()
    print("\n✅ Graph traverser test complete.")
