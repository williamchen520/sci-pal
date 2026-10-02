"""
Deduplicate papers in research.db.
V21.6 - Paper de-duplication

The documents/ folder contains a few PDFs that are the same paper under two
filenames (same DOI / same title). They were parsed into two different
paper_id rows, which (a) duplicates evidence in retrieval and (b) inflates the
cross-paper graph.

This script:
  1. finds duplicate groups, first by normalized DOI, then by normalized title
     (null / "N/A" / very short titles are not used as keys);
  2. picks a canonical keeper per group = richest parse
     (most paragraphs, then figures, then citations, then cleaner filename);
  3. dry-run by default: only prints what it would remove;
  4. with --apply: atomically deletes the loser rows from every SQLite table
     (paragraphs/figures/tables/citations/paper_index/cross_paper_index/papers
     and both FTS5 tables) and prunes their vectors from all Chroma collections.

Usage:
  python -m build_db.dedup_papers            # safe preview, changes nothing
  python -m build_db.dedup_papers --apply    # actually remove duplicates
  python -m build_db.dedup_papers --apply --vacuum
"""
import re
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

# Tables that carry a plain paper_id column.
PAPER_ID_TABLES = ["paragraphs", "figures", "tables", "citations", "paper_index"]


def norm_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    d = d.strip(".,;)] ").strip()
    return d


def norm_title(title: str) -> str:
    if not title:
        return ""
    t = title.strip().lower()
    if t in ("n/a", "na", "none", "null"):
        return ""
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    # Too short / placeholder titles are not safe dedup keys.
    if len(t) < 15 or len(t.split()) < 4:
        return ""
    return t


def find_groups(conn) -> dict:
    """Return {key: [row, ...]} for groups with >1 paper."""
    rows = conn.execute(
        """SELECT p.paper_id, p.filename, p.title, p.doi,
                  (SELECT COUNT(*) FROM paragraphs x WHERE x.paper_id=p.paper_id) AS n_para,
                  (SELECT COUNT(*) FROM figures    x WHERE x.paper_id=p.paper_id) AS n_fig,
                  (SELECT COUNT(*) FROM citations  x WHERE x.paper_id=p.paper_id) AS n_cite
           FROM papers p"""
    ).fetchall()

    buckets = defaultdict(list)
    for r in rows:
        key = None
        d = norm_doi(r["doi"])
        if d:
            key = ("doi", d)
        else:
            t = norm_title(r["title"])
            if t:
                key = ("title", t)
        if key:
            buckets[key].append(r)
    return {k: v for k, v in buckets.items() if len(v) > 1}


def pick_canonical(members: list):
    """Richest parse wins; filename cleanliness is the final tie-breaker."""
    def score(r):
        # Fewer spaces / no double-space / shorter basename = cleaner source file
        fname = r["filename"] or ""
        messy = fname.count("  ") + fname.count(" ")
        return (r["n_para"], r["n_fig"], r["n_cite"], -messy, -len(fname))
    return max(members, key=score)


def preview(conn, groups: dict):
    print("=" * 64)
    print(f"🔎 Duplicate scan — found {len(groups)} duplicate group(s)")
    print("=" * 64)
    total_losers = 0
    for key, members in groups.items():
        keep = pick_canonical(members)
        print(f"\n● key={key[0]}:{key[1]}")
        for r in members:
            tag = "KEEP ✅" if r["paper_id"] == keep["paper_id"] else "DROP ❌"
            print(f"   [{tag}] paras={r['n_para']:>4} figs={r['n_fig']:>3} "
                  f"cites={r['n_cite']:>4}  {r['filename']}")
        total_losers += len(members) - 1
    print("\n" + "-" * 64)
    print(f"Would remove {total_losers} duplicate paper(s); "
          f"{sum(len(v) for v in groups.values()) - total_losers} canonical kept.")
    print("This was a DRY RUN. Re-run with --apply to delete.")


def apply(conn, groups: dict, do_vacuum: bool):
    losers = []
    for members in groups.values():
        keep = pick_canonical(members)
        for r in members:
            if r["paper_id"] != keep["paper_id"]:
                losers.append((r["paper_id"], r["filename"], keep["filename"]))

    # --- SQLite (one atomic transaction) ---
    cur = conn.cursor()
    counts = defaultdict(int)
    try:
        cur.execute("BEGIN")
        for pid, fname, _ in losers:
            for tbl in PAPER_ID_TABLES:
                cur.execute(f"DELETE FROM {tbl} WHERE paper_id = ?", (pid,))
                counts[tbl] += cur.rowcount
            cur.execute("DELETE FROM cross_paper_index WHERE source_paper_id=? OR target_paper_id=?",
                        (pid, pid))
            counts["cross_paper_index"] += cur.rowcount
            # FTS5 content-bearing tables
            cur.execute("DELETE FROM paragraphs_fts WHERE paper_id = ?", (pid,))
            counts["paragraphs_fts"] += cur.rowcount
            cur.execute("DELETE FROM papers_fts WHERE paper_id = ?", (pid,))
            counts["papers_fts"] += cur.rowcount
            cur.execute("DELETE FROM papers WHERE paper_id = ?", (pid,))
            counts["papers"] += cur.rowcount
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ SQLite deletion failed, rolled back: {e}")
        return

    print("SQLite removed:")
    for k in PAPER_ID_TABLES + ["cross_paper_index", "paragraphs_fts", "papers_fts", "papers"]:
        if counts[k]:
            print(f"   {k}: {counts[k]}")

    # --- Chroma vectors (regenerable; pruned to free space) ---
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        for pid, fname, _ in losers:
            for name in ("paragraphs", "figures", "tables"):
                try:
                    col = client.get_collection(name)
                    col.delete(where={"paper_id": pid})
                except Exception:
                    pass
            try:
                client.get_collection("papers").delete(ids=[pid])
            except Exception:
                pass
        print("✅ Chroma vectors pruned.")
    except Exception as e:
        print(f"⚠️  Chroma pruning skipped/failed ({e}). "
              f"Rerun build_embeddings to reconcile.")

    if do_vacuum:
        print("Vacuuming SQLite ...")
        conn.execute("VACUUM")
    print(f"\n✅ Removed {len(losers)} duplicate paper(s).")
    for pid, fname, kept in losers:
        print(f"   dropped {fname}  (kept {kept})")


def main():
    do_apply = "--apply" in sys.argv
    do_vacuum = "--vacuum" in sys.argv
    if not DB_PATH.exists():
        print(f"❌ DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    groups = find_groups(conn)
    if not groups:
        print("✅ No duplicate papers found.")
        return

    if do_apply:
        apply(conn, groups, do_vacuum)
    else:
        preview(conn, groups)


if __name__ == "__main__":
    main()
