"""
Build figure/table → paragraph DESCRIBED_IN links, and fix fig_number /
table_number from caption text.
V22.2 - Figure-table binding.

Two jobs in one script (both read-only by default, --apply to write):

1. **Fix numbering**:  figures.fig_number and tables.table_number are assigned
   as "Fig N" / "Table N" by Docling's encounter order, which often differs
   from the paper's true numbering. The caption text carries the true number
   ("Figure 3. ...", "Table 1. ..."). Parse it and update the stored number.

2. **Build DESCRIBED_IN edges**:  scan body paragraphs for in-text references
   ("Figure 3 shows...", "(Fig. 2A)", "Table 1 summarises...") and link each
   paragraph to the figure(s)/table(s) it discusses. Edges are stored in
   paper_index (source_type='paragraph', target_type='figure'/'table',
   relation='DESCRIBED_IN').

Usage:
  python -m build_db.build_figure_links            # dry-run audit
  python -m build_db.build_figure_links --apply    # write fixes + edges
"""
import sqlite3
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# True number inside a caption: "Figure 3.", "Fig. 2A:", "Fig 10 —", "Table 1."
CAPTION_FIG_NUM = re.compile(
    r'^\s*Fig(?:ure)?\.?\s*(\d+)([a-z])?[\.\:\s—\-]', re.IGNORECASE)
CAPTION_TAB_NUM = re.compile(
    r'^\s*Tab(?:le)?\.?\s*(\d+)([a-z])?[\.\:\s—\-]', re.IGNORECASE)

# In-text figure references: "Figure 3", "Fig. 2A", "Figs. 1-3", "(Fig. 4)", "Figures 5"
INTEXT_FIG = re.compile(
    r'\bFig(?:ures?|s\.|\.)?\s*(\d+)([a-z])?(?:\s*[-–—]\s*(\d+))?',
    re.IGNORECASE)
# In-text table references: "Table 1", "Tab. 2", "Tables 1-3"
INTEXT_TAB = re.compile(
    r'\bTab(?:les?|s\.|\.)?\s*(\d+)(?:\s*[-–—]\s*(\d+))?',
    re.IGNORECASE)

# Words that indicate a caption paragraph (not body text) — skip these when
# scanning for in-text references.
CAPTION_LINE = re.compile(
    r'^\s*(Fig(?:ure)?|Tab(?:le)?)\s*\d+', re.IGNORECASE)


def fix_numbering(conn, apply: bool) -> dict:
    """Fix fig_number / table_number from caption text. Returns stats."""
    stats = {"fig_fixed": 0, "fig_ambiguous": 0, "fig_no_caption": 0,
             "tab_fixed": 0, "tab_ambiguous": 0, "tab_no_caption": 0}

    # --- Figures ---
    rows = conn.execute(
        "SELECT fig_id, paper_id, fig_number, caption FROM figures"
    ).fetchall()
    for fig_id, paper_id, stored_num, caption in rows:
        if not caption or not caption.strip():
            stats["fig_no_caption"] += 1
            continue
        m = CAPTION_FIG_NUM.match(caption)
        if not m:
            stats["fig_ambiguous"] += 1
            continue
        true_num = f"Fig {m.group(1)}" + (m.group(2) or "")
        if true_num != stored_num:
            stats["fig_fixed"] += 1
            if apply:
                conn.execute(
                    "UPDATE figures SET fig_number = ? WHERE fig_id = ?",
                    (true_num, fig_id))

    # --- Tables ---
    rows = conn.execute(
        "SELECT table_id, paper_id, table_number, caption FROM tables"
    ).fetchall()
    for table_id, paper_id, stored_num, caption in rows:
        if not caption or not caption.strip():
            stats["tab_no_caption"] += 1
            continue
        m = CAPTION_TAB_NUM.match(caption)
        if not m:
            stats["tab_ambiguous"] += 1
            continue
        true_num = f"Table {m.group(1)}" + (m.group(2) or "")
        if true_num != stored_num:
            stats["tab_fixed"] += 1
            if apply:
                conn.execute(
                    "UPDATE tables SET table_number = ? WHERE table_id = ?",
                    (true_num, table_id))

    return stats


def build_described_in(conn, apply: bool) -> dict:
    """Scan body paragraphs and build DESCRIBED_IN edges. Returns stats."""
    stats = {"paragraphs_scanned": 0, "fig_refs_found": 0,
             "tab_refs_found": 0, "fig_edges_created": 0,
             "tab_edges_created": 0, "unmatched_fig_refs": 0,
             "unmatched_tab_refs": 0}

    # Build lookup: paper_id -> {normalized_number: fig_id}
    fig_lookup: dict[str, dict[str, str]] = {}
    for fig_id, paper_id, fig_number in conn.execute(
            "SELECT fig_id, paper_id, fig_number FROM figures"):
        if not fig_number:
            continue
        # Normalize: "Fig 3" -> "3", "Fig 2A" -> "2a"
        norm = re.sub(r'^Fig\s*', '', fig_number, flags=re.IGNORECASE).lower()
        fig_lookup.setdefault(paper_id, {})[norm] = fig_id

    tab_lookup: dict[str, dict[str, str]] = {}
    for table_id, paper_id, table_number in conn.execute(
            "SELECT table_id, paper_id, table_number FROM tables"):
        if not table_number:
            continue
        norm = re.sub(r'^Table\s*', '', table_number, flags=re.IGNORECASE).lower()
        tab_lookup.setdefault(paper_id, {})[norm] = table_id

    # Get all body paragraphs (skip reference sections — they're already
    # excluded from QA retrieval, but we skip them here too for cleanliness).
    from services.search.reference_filter import is_reference_entry
    rows = conn.execute("""
        SELECT para_id, paper_id, section_level1, section_level2, text
        FROM paragraphs
        ORDER BY paper_id, sequence
    """).fetchall()

    edges: list[tuple] = []  # (paper_id, source_type, source_id, target_type, target_id, relation)
    seen_edges = set()

    for para_id, paper_id, sec_l1, sec_l2, text in rows:
        if not text or not text.strip():
            continue
        # Skip reference sections
        if is_reference_entry(text, sec_l1, sec_l2):
            continue
        # Skip caption paragraphs themselves
        first_line = text.strip().split("\n")[0]
        if CAPTION_LINE.match(first_line):
            continue

        stats["paragraphs_scanned"] += 1

        paper_figs = fig_lookup.get(paper_id, {})
        paper_tabs = tab_lookup.get(paper_id, {})

        # --- Figure references ---
        for m in INTEXT_FIG.finditer(text):
            stats["fig_refs_found"] += 1
            start_num = m.group(1)
            suffix = (m.group(2) or "").lower()
            end_num = m.group(3)

            nums = [start_num + suffix]
            if end_num and end_num != start_num:
                # Range: Figs. 1-3 → 1, 2, 3 (only if no suffix)
                if not suffix:
                    try:
                        nums = [str(n) for n in range(int(start_num), int(end_num) + 1)]
                    except ValueError:
                        pass

            for num in nums:
                fig_id = paper_figs.get(num.lower())
                if fig_id:
                    edge_key = (para_id, "figure", fig_id)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append((paper_id, "paragraph", para_id,
                                      "figure", fig_id, "DESCRIBED_IN"))
                        stats["fig_edges_created"] += 1
                else:
                    stats["unmatched_fig_refs"] += 1

        # --- Table references ---
        for m in INTEXT_TAB.finditer(text):
            stats["tab_refs_found"] += 1
            start_num = m.group(1)
            end_num = m.group(2)

            nums = [start_num]
            if end_num and end_num != start_num:
                try:
                    nums = [str(n) for n in range(int(start_num), int(end_num) + 1)]
                except ValueError:
                    pass

            for num in nums:
                table_id = paper_tabs.get(num.lower())
                if table_id:
                    edge_key = (para_id, "table", table_id)
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append((paper_id, "paragraph", para_id,
                                      "table", table_id, "DESCRIBED_IN"))
                        stats["tab_edges_created"] += 1
                else:
                    stats["unmatched_tab_refs"] += 1

    if apply and edges:
        # Clear old DESCRIBED_IN edges first (idempotent re-run)
        conn.execute("DELETE FROM paper_index WHERE relation = 'DESCRIBED_IN'")
        rows_with_id = []
        for paper_id, src_type, src_id, tgt_type, tgt_id, rel in edges:
            idx_id = f"idx_{paper_id[:15]}_{src_id[-10:]}_{tgt_id[-10:]}"
            rows_with_id.append(
                (idx_id, paper_id, src_id, src_type, tgt_id, tgt_type, rel))
        conn.executemany("""
            INSERT OR IGNORE INTO paper_index
            (index_id, paper_id, source_id, source_type, target_id, target_type, relation)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows_with_id)

    return stats


def main():
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    print("=" * 64)
    print("🔗 Figure/Table → Paragraph DESCRIBED_IN Builder (V22.2)")
    print("=" * 64)
    print(f"Mode: {'APPLY (writing changes)' if apply else 'DRY-RUN (read-only)'}")
    print()

    # Step 1: Fix numbering
    print("── Step 1: Fix fig_number / table_number from captions ──")
    num_stats = fix_numbering(conn, apply)
    print(f"  Figures: {num_stats['fig_fixed']} fixed, "
          f"{num_stats['fig_ambiguous']} ambiguous (no parseable number), "
          f"{num_stats['fig_no_caption']} no caption")
    print(f"  Tables:  {num_stats['tab_fixed']} fixed, "
          f"{num_stats['tab_ambiguous']} ambiguous, "
          f"{num_stats['tab_no_caption']} no caption")
    print()

    # Step 2: Build DESCRIBED_IN edges (always run after numbering fix,
    # even in dry-run, so the audit shows what WOULD be created)
    print("── Step 2: Build DESCRIBED_IN edges ──")
    edge_stats = build_described_in(conn, apply)
    print(f"  Paragraphs scanned:     {edge_stats['paragraphs_scanned']}")
    print(f"  Figure refs found:      {edge_stats['fig_refs_found']}")
    print(f"  Table refs found:       {edge_stats['tab_refs_found']}")
    print(f"  Figure edges created:   {edge_stats['fig_edges_created']}")
    print(f"  Table edges created:    {edge_stats['tab_edges_created']}")
    print(f"  Unmatched figure refs:  {edge_stats['unmatched_fig_refs']}")
    print(f"  Unmatched table refs:   {edge_stats['unmatched_tab_refs']}")
    print()

    if apply:
        conn.commit()
        print("✅ Changes committed to database.")
    else:
        print("ℹ️  Dry-run — no changes written. Re-run with --apply to commit.")

    conn.close()


if __name__ == "__main__":
    main()
