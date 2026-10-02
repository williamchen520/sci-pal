"""
Build paper communities from the SIMILAR-edge graph.
V24.3 - Leiden / Louvain community detection + auto-summaries

Reads SIMILAR edges from cross_paper_index, builds an undirected graph,
runs community detection (Leiden if available, else Louvain/greedy
modularity), picks a representative paper per community, and generates
a short summary from title + keywords + abstract.

Usage:
  python -m build_db.build_communities            # dry-run (stats only)
  python -m build_db.build_communities --apply    # write to DB
  python -m build_db.build_communities --resolution 1.0  # community granularity
"""
import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "research.db"


def get_communities_table_ddl() -> str:
    return """
    CREATE TABLE IF NOT EXISTS paper_communities (
        community_id    TEXT PRIMARY KEY,
        size            INTEGER DEFAULT 0,
        representative_paper_id TEXT,
        summary         TEXT,
        keywords        TEXT,
        avg_year        REAL,
        created_at      TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS community_members (
        community_id    TEXT NOT NULL,
        paper_id        TEXT NOT NULL,
        centrality      REAL DEFAULT 0.0,
        PRIMARY KEY (community_id, paper_id),
        FOREIGN KEY (community_id) REFERENCES paper_communities(community_id)
    );
    CREATE INDEX IF NOT EXISTS idx_community_members_paper
        ON community_members(paper_id);
    """


def detect_communities(edges: List[Tuple[str, str, float]],
                       resolution: float = 1.0
                       ) -> Tuple[List[Set[str]], str]:
    """
    Run community detection on the edge list.
    Returns (list of communities, algorithm_name).

    Tries Leiden (leidenalg + igraph) first, falls back to Louvain
    (networkx greedy_modularity_communities).
    """
    # Build node set
    nodes = set()
    for src, dst, _ in edges:
        nodes.add(src)
        nodes.add(dst)

    # Try Leiden first
    try:
        import igraph as ig
        import leidenalg

        # Build igraph graph
        node_list = sorted(nodes)
        node_idx = {n: i for i, n in enumerate(node_list)}
        g = ig.Graph()
        g.add_vertices(len(node_list))
        g.vs["name"] = node_list
        edge_list = [(node_idx[src], node_idx[dst])
                     for src, dst, _ in edges]
        g.add_edges(edge_list)
        g.es["weight"] = [w for _, _, w in edges]

        # Run Leiden
        partition = leidenalg.find_partition(
            g, leidenalg.ModularityVertexPartition,
            weights="weight", resolution_parameter=resolution
        )
        communities = []
        for cluster in partition:
            communities.append({node_list[i] for i in cluster})
        return communities, "Leiden (leidenalg)"
    except ImportError:
        pass
    except Exception as e:
        print(f"  ⚠️  Leiden failed ({e}), falling back to Louvain")

    # Fallback: networkx greedy modularity (Louvain approximation)
    try:
        import networkx as nx
        from networkx.algorithms.community import greedy_modularity_communities

        G = nx.Graph()
        G.add_nodes_from(nodes)
        for src, dst, w in edges:
            G.add_edge(src, dst, weight=w)

        communities = list(greedy_modularity_communities(
            G, weight="weight", resolution=resolution))
        return [set(c) for c in communities], "Louvain (networkx greedy_modularity)"
    except ImportError:
        print("  ❌ Neither leidenalg nor networkx available.")
        print("     Install: pip install networkx  (or pip install igraph leidenalg)")
        sys.exit(1)


def compute_centrality(edges: List[Tuple[str, str, float]],
                       community: Set[str]) -> Dict[str, float]:
    """Compute degree centrality within the community subgraph."""
    try:
        import networkx as nx
        G = nx.Graph()
        for src, dst, w in edges:
            if src in community and dst in community:
                G.add_edge(src, dst, weight=w)
        if G.number_of_nodes() == 0:
            return {n: 0.0 for n in community}
        # Degree centrality within subgraph
        centrality = nx.degree_centrality(G)
        return {n: centrality.get(n, 0.0) for n in community}
    except ImportError:
        # Fallback: simple degree count
        degree = {n: 0 for n in community}
        for src, dst, _ in edges:
            if src in community and dst in community:
                degree[src] = degree.get(src, 0) + 1
                degree[dst] = degree.get(dst, 0) + 1
        max_deg = max(degree.values()) if degree else 1
        return {n: d / max_deg for n, d in degree.items()}


def generate_summary(conn: sqlite3.Connection,
                     paper_id: str,
                     community: Set[str]) -> Tuple[str, str]:
    """
    Generate a short summary for a community based on its representative
    paper and the collective keywords.
    Returns (summary, keywords_csv).
    """
    # Get representative paper info
    rep = conn.execute(
        "SELECT title, authors, journal, year, keywords FROM papers WHERE paper_id = ?",
        (paper_id,)
    ).fetchone()
    if not rep:
        return "No representative paper found.", ""

    title = rep["title"] or "Untitled"
    journal = rep["journal"] or ""
    year = rep["year"] or "?"
    rep_keywords = rep["keywords"] or ""

    # Collect all keywords from community members
    all_keywords = []
    if rep_keywords:
        all_keywords.extend([k.strip() for k in rep_keywords.split(",") if k.strip()])

    placeholders = ",".join("?" * len(community))
    rows = conn.execute(
        f"SELECT keywords FROM papers WHERE paper_id IN ({placeholders})",
        list(community)
    ).fetchall()
    for r in rows:
        if r["keywords"]:
            for k in r["keywords"].split(","):
                k = k.strip()
                if k and k not in all_keywords:
                    all_keywords.append(k)

    # Build summary
    summary_parts = [
        f"Community of {len(community)} papers.",
        f"Representative: \"{title[:120]}\"",
    ]
    if journal or year:
        summary_parts.append(f"Published in {journal} ({year}).")
    if all_keywords[:8]:
        summary_parts.append(f"Key topics: {', '.join(all_keywords[:8])}.")

    summary = " ".join(summary_parts)
    keywords_csv = ", ".join(all_keywords[:15])

    return summary, keywords_csv


def main():
    parser = argparse.ArgumentParser(description="Build paper communities")
    parser.add_argument("--apply", action="store_true", help="Write to DB")
    parser.add_argument("--resolution", type=float, default=1.0,
                        help="Community resolution (higher = more, smaller communities)")
    parser.add_argument("--min-size", type=int, default=2,
                        help="Minimum community size to keep")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print("=" * 60)
    print(f"🕸️  Community Builder (V24.3) — {mode}")
    print("=" * 60)
    print(f"  resolution={args.resolution}, min_size={args.min_size}")

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Read SIMILAR edges
    print("\n── Reading SIMILAR edges ──")
    rows = conn.execute("""
        SELECT source_paper_id, target_paper_id, confidence
        FROM cross_paper_index
        WHERE relation = 'similar'
    """).fetchall()
    edges = [(r["source_paper_id"], r["target_paper_id"],
              r["confidence"] or 0.5) for r in rows]
    print(f"  {len(edges)} SIMILAR edges")

    if not edges:
        print("  ⚠️  No SIMILAR edges found. Run build_paper_graph --apply first.")
        conn.close()
        return

    # Detect communities
    print(f"\n── Detecting communities ──")
    communities, algo = detect_communities(edges, args.resolution)
    print(f"  Algorithm: {algo}")
    print(f"  Raw communities: {len(communities)}")

    # Filter by min size
    communities = [c for c in communities if len(c) >= args.min_size]
    # Sort by size descending
    communities.sort(key=len, reverse=True)
    print(f"  After min_size={args.min_size} filter: {len(communities)} communities")

    # Stats
    sizes = [len(c) for c in communities]
    total_assigned = sum(sizes)
    all_nodes = set()
    for src, dst, _ in edges:
        all_nodes.add(src)
        all_nodes.add(dst)
    isolated = len(all_nodes) - total_assigned

    print(f"\n── Community statistics ──")
    print(f"  Nodes in graph:    {len(all_nodes)}")
    print(f"  Nodes assigned:    {total_assigned} ({100*total_assigned/len(all_nodes):.1f}%)")
    print(f"  Isolated nodes:    {isolated}")
    print(f"  Largest community: {max(sizes) if sizes else 0}")
    print(f"  Smallest:          {min(sizes) if sizes else 0}")
    print(f"  Avg size:          {sum(sizes)/len(sizes):.1f}" if sizes else "  Avg size: 0")

    print(f"\n  Top 10 communities:")
    for i, comm in enumerate(communities[:10]):
        # Get representative (first paper title)
        pid = next(iter(comm))
        row = conn.execute(
            "SELECT title FROM papers WHERE paper_id = ?", (pid,)
        ).fetchone()
        title = (row["title"] or "?")[:60] if row else "?"
        print(f"    [{i+1:2d}] size={len(comm):3d} | {title}...")

    if not args.apply:
        print(f"\n  💡 Dry-run complete. Run with --apply to write to DB.")
        conn.close()
        return

    # Write to SQLite
    print(f"\n── Writing to SQLite ──")
    conn.executescript(get_communities_table_ddl())
    conn.execute("DELETE FROM community_members")
    conn.execute("DELETE FROM paper_communities")

    written = 0
    for i, comm in enumerate(communities):
        comm_id = f"comm_{i+1:03d}"

        # Compute centrality and find representative
        centrality = compute_centrality(edges, comm)
        rep_pid = max(comm, key=lambda p: centrality.get(p, 0.0))

        # Generate summary
        summary, keywords = generate_summary(conn, rep_pid, comm)

        # Compute avg year
        placeholders = ",".join("?" * len(comm))
        year_rows = conn.execute(
            f"SELECT year FROM papers WHERE paper_id IN ({placeholders}) AND year IS NOT NULL",
            list(comm)
        ).fetchall()
        years = [r["year"] for r in year_rows if r["year"]]
        avg_year = sum(years) / len(years) if years else 0

        conn.execute("""
            INSERT OR REPLACE INTO paper_communities
            (community_id, size, representative_paper_id, summary, keywords, avg_year)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (comm_id, len(comm), rep_pid, summary, keywords, avg_year))

        for pid in comm:
            conn.execute("""
                INSERT OR REPLACE INTO community_members
                (community_id, paper_id, centrality)
                VALUES (?, ?, ?)
            """, (comm_id, pid, centrality.get(pid, 0.0)))

        written += 1

    conn.commit()
    print(f"  ✅ {written} communities written to paper_communities table")
    print(f"  ✅ {sum(len(c) for c in communities)} memberships written")

    conn.close()
    print(f"\n✅ Community build complete.")


if __name__ == "__main__":
    main()
