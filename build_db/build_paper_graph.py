"""
Build the paper-level citation + similarity graph.
V22.3 - Paper graph for T3 graph traversal.

Builds two edge types in cross_paper_index:

1. **CITES** (directed):  paper A cites paper B.  Matched by DOI first
   (confidence 0.95), then by normalized title (confidence 0.70).  Self-
   citations and citations to papers not in the corpus are skipped.

2. **SIMILAR** (undirected):  paper A is semantically similar to paper B,
   based on abstract/title embedding cosine similarity in the Chroma `papers`
   collection.  Only edges above --similar-threshold (default 0.50) are kept.
   Stored in both directions for query convenience.

After building, prints graph statistics: node count, edge counts by type,
degree distribution (top-cited / most-similar papers), connected components,
and largest component size.

Usage:
  python -m build_db.build_paper_graph                       # dry-run audit
  python -m build_db.build_paper_graph --apply               # write edges
  python -m build_db.build_paper_graph --similar-threshold 0.6
"""
import sqlite3
import re
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

DEFAULT_SIMILAR_THRESHOLD = 0.50
SIMILAR_TOP_K = 10  # nearest neighbors to consider per paper


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def build_cites_edges(conn) -> tuple[list, dict]:
    """Rebuild CITES edges from citations table. Returns (edges, stats)."""
    stats = {"citations_total": 0, "citations_with_doi": 0,
             "doi_matches": 0, "title_matches": 0, "self_cites": 0,
             "unmatched": 0}

    # Build lookup: doi -> paper_id, normalized_title -> [paper_id]
    doi_lookup: dict[str, str] = {}
    title_lookup: dict[str, list[str]] = defaultdict(list)
    for paper_id, doi, title in conn.execute(
            "SELECT paper_id, doi, title FROM papers"):
        if doi:
            doi_lookup[doi.strip().lower()] = paper_id
        nt = normalize_title(title)
        if nt and len(nt) > 10:  # skip very short titles
            title_lookup[nt].append(paper_id)

    edges: list[tuple] = []  # (source, target, relation, confidence)
    seen = set()

    for source_id, ref_number, raw_text, doi, title in conn.execute(
            "SELECT paper_id, ref_number, raw_text, doi, title FROM citations"):
        stats["citations_total"] += 1
        target_id = None
        confidence = 0.0

        # 1. DOI match (highest confidence)
        if doi and doi.strip():
            stats["citations_with_doi"] += 1
            target_id = doi_lookup.get(doi.strip().lower())
            if target_id:
                confidence = 0.95
                stats["doi_matches"] += 1

        # 2. Title match (fallback)
        if not target_id and title:
            nt = normalize_title(title)
            if nt in title_lookup:
                candidates = title_lookup[nt]
                # Prefer a candidate that isn't the source paper
                target_id = next((p for p in candidates if p != source_id), candidates[0])
                confidence = 0.70
                stats["title_matches"] += 1

        if not target_id:
            stats["unmatched"] += 1
            continue

        if target_id == source_id:
            stats["self_cites"] += 1
            continue

        edge_key = (source_id, target_id, "cites")
        if edge_key not in seen:
            seen.add(edge_key)
            edges.append((source_id, target_id, "cites", confidence))

    return edges, stats


def build_similar_edges(conn, threshold: float) -> tuple[list, dict]:
    """Build SIMILAR edges from Chroma paper embeddings. Returns (edges, stats)."""
    stats = {"papers_in_chroma": 0, "pairs_above_threshold": 0,
             "pairs_below_threshold": 0}

    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        paper_collection = client.get_collection("papers")
    except Exception:
        print("  ⚠️  Chroma 'papers' collection not found — skipping SIMILAR edges")
        return [], stats

    # Get all paper IDs
    all_ids = paper_collection.get()["ids"]
    stats["papers_in_chroma"] = len(all_ids)

    edges: list[tuple] = []
    seen = set()

    for paper_id in all_ids:
        results = paper_collection.query(
            query_embeddings=paper_collection.get(ids=[paper_id], include=["embeddings"])["embeddings"],
            n_results=min(SIMILAR_TOP_K + 1, len(all_ids)),
        )
        for i, neighbor_id in enumerate(results["ids"][0]):
            if neighbor_id == paper_id:
                continue
            distance = results["distances"][0][i]
            similarity = 1.0 - distance  # cosine similarity
            if similarity >= threshold:
                stats["pairs_above_threshold"] += 1
                # Store both directions for query convenience
                for src, tgt in [(paper_id, neighbor_id), (neighbor_id, paper_id)]:
                    edge_key = (src, tgt, "similar")
                    if edge_key not in seen:
                        seen.add(edge_key)
                        edges.append((src, tgt, "similar", round(similarity, 4)))
            else:
                stats["pairs_below_threshold"] += 1

    return edges, stats


def compute_graph_stats(conn) -> dict:
    """Compute graph statistics from cross_paper_index."""
    n_papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    n_cites = conn.execute(
        "SELECT COUNT(*) FROM cross_paper_index WHERE relation='cites'").fetchone()[0]
    n_similar = conn.execute(
        "SELECT COUNT(*) FROM cross_paper_index WHERE relation='similar'").fetchone()[0]

    # Top cited papers (in-degree for cites)
    top_cited = conn.execute("""
        SELECT p.title, COUNT(*) as cite_count
        FROM cross_paper_index c
        JOIN papers p ON p.paper_id = c.target_paper_id
        WHERE c.relation='cites'
        GROUP BY c.target_paper_id
        ORDER BY cite_count DESC
        LIMIT 5
    """).fetchall()

    # Degree distribution for similar edges (count unique neighbors)
    similar_degrees = conn.execute("""
        SELECT source_paper_id, COUNT(DISTINCT target_paper_id) as deg
        FROM cross_paper_index WHERE relation='similar'
        GROUP BY source_paper_id
    """).fetchall()
    degrees = [r[1] for r in similar_degrees]
    avg_degree = sum(degrees) / len(degrees) if degrees else 0
    max_degree = max(degrees) if degrees else 0

    # Connected components (treat both edge types as undirected)
    adj: dict[str, set] = defaultdict(set)
    for src, tgt in conn.execute(
            "SELECT source_paper_id, target_paper_id FROM cross_paper_index"):
        adj[src].add(tgt)
        adj[tgt].add(src)

    visited = set()
    components = []
    for node in adj:
        if node not in visited:
            # BFS
            comp = []
            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                comp.append(n)
                stack.extend(adj[n] - visited)
            components.append(comp)

    # Papers with no edges (isolated nodes)
    all_paper_ids = set(r[0] for r in conn.execute("SELECT paper_id FROM papers"))
    connected_nodes = set(adj.keys())
    isolated = len(all_paper_ids - connected_nodes)

    largest_comp = max(len(c) for c in components) if components else 0

    return {
        "n_papers": n_papers,
        "n_cites_edges": n_cites,
        "n_similar_edges": n_similar,
        "top_cited": [(r[0][:60], r[1]) for r in top_cited],
        "similar_avg_degree": round(avg_degree, 2),
        "similar_max_degree": max_degree,
        "n_components": len(components),
        "largest_component": largest_comp,
        "isolated_papers": isolated,
    }


def main():
    apply = "--apply" in sys.argv
    threshold = DEFAULT_SIMILAR_THRESHOLD
    for arg in sys.argv[1:]:
        if arg.startswith("--similar-threshold="):
            threshold = float(arg.split("=", 1)[1])

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    print("=" * 64)
    print("🕸️  Paper Graph Builder (V22.3)")
    print("=" * 64)
    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"Similarity threshold: {threshold}")
    print()

    # Step 1: CITES edges
    print("── Step 1: CITES edges (DOI → title matching) ──")
    cites_edges, cites_stats = build_cites_edges(conn)
    print(f"  Citations scanned:    {cites_stats['citations_total']}")
    print(f"  Citations with DOI:   {cites_stats['citations_with_doi']}")
    print(f"  DOI matches:          {cites_stats['doi_matches']}")
    print(f"  Title matches:        {cites_stats['title_matches']}")
    print(f"  Self-citations:       {cites_stats['self_cites']}")
    print(f"  Unmatched:            {cites_stats['unmatched']}")
    print(f"  Unique CITES edges:   {len(cites_edges)}")
    print()

    # Step 2: SIMILAR edges
    print("── Step 2: SIMILAR edges (Chroma abstract cosine) ──")
    similar_edges, similar_stats = build_similar_edges(conn, threshold)
    print(f"  Papers in Chroma:     {similar_stats['papers_in_chroma']}")
    print(f"  Pairs above threshold:{similar_stats['pairs_above_threshold']}")
    print(f"  Unique SIMILAR edges: {len(similar_edges)} (both directions)")
    print()

    # Write
    if apply:
        print("── Writing to cross_paper_index ──")
        conn.execute("DELETE FROM cross_paper_index")
        all_edges = cites_edges + similar_edges
        rows = []
        for i, (src, tgt, rel, conf) in enumerate(all_edges):
            link_id = f"graph_{i:06d}"
            rows.append((link_id, src, tgt, rel, conf))
        conn.executemany("""
            INSERT OR REPLACE INTO cross_paper_index
            (link_id, source_paper_id, target_paper_id, relation, confidence)
            VALUES (?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
        print(f"  ✅ {len(rows)} edges written")
        print()

    # Step 3: Graph stats (always compute, even in dry-run — uses existing DB)
    print("── Graph statistics ──")
    stats = compute_graph_stats(conn)
    print(f"  Papers (nodes):           {stats['n_papers']}")
    print(f"  CITES edges:              {stats['n_cites_edges']}")
    print(f"  SIMILAR edges:            {stats['n_similar_edges']}")
    print(f"  Connected components:     {stats['n_components']}")
    print(f"  Largest component:        {stats['largest_component']} papers")
    print(f"  Isolated papers:          {stats['isolated_papers']}")
    print(f"  Similar avg degree:       {stats['similar_avg_degree']}")
    print(f"  Similar max degree:       {stats['similar_max_degree']}")
    if stats['top_cited']:
        print(f"  Top cited papers:")
        for title, count in stats['top_cited']:
            print(f"    [{count}x] {title}")
    print()

    if not apply:
        print("ℹ️  Dry-run — no changes written. Re-run with --apply to commit.")

    conn.close()


if __name__ == "__main__":
    main()
