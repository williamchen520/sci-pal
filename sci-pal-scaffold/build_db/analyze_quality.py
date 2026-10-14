"""
Quality analysis for Sci-Pal database.
V20.0 — inspect parsing quality across all papers.
"""
import sqlite3
from pathlib import Path
from collections import Counter

project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "research.db"

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print("🔬 Sci-Pal Parsing Quality Analysis — V20.0")
print("=" * 70)

# ── 1. Figure caption quality ──────────────────────────────────────────────
print("\n📊 1. Figure Caption Quality")
print("-" * 50)
cur.execute("SELECT COUNT(*) FROM figures")
total_figs = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM figures WHERE caption IS NULL OR caption = '' OR caption = 'No caption...'")
no_caption = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM figures WHERE caption IS NOT NULL AND caption != '' AND caption != 'No caption...'")
with_caption = cur.fetchone()[0]
print(f"  Total figures:     {total_figs}")
print(f"  With caption:      {with_caption} ({with_caption/total_figs*100:.1f}%)")
print(f"  Without caption:    {no_caption} ({no_caption/total_figs*100:.1f}%)")

# ── 2. Paragraph quality ──────────────────────────────────────────────────
print("\n📊 2. Paragraph Quality")
print("-" * 50)
cur.execute("SELECT COUNT(*) FROM paragraphs")
total_paras = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM paragraphs WHERE LENGTH(text) < 50")
short_paras = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM paragraphs WHERE LENGTH(text) > 500")
long_paras = cur.fetchone()[0]
cur.execute("SELECT AVG(LENGTH(text)) FROM paragraphs")
avg_len = cur.fetchone()[0]
print(f"  Total paragraphs:  {total_paras}")
print(f"  Average length:    {avg_len:.0f} chars")
print(f"  Short (<50 chars): {short_paras} ({short_paras/total_paras*100:.1f}%)")
print(f"  Long (>500 chars): {long_paras} ({long_paras/total_paras*100:.1f}%)")

# ── 3. Section hierarchy ───────────────────────────────────────────────────
print("\n📊 3. Section Hierarchy")
print("-" * 50)
cur.execute("SELECT COUNT(DISTINCT paper_id) FROM paragraphs WHERE section_level1 IS NOT NULL AND section_level1 != ''")
papers_l1 = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT paper_id) FROM paragraphs WHERE section_level2 IS NOT NULL AND section_level2 != ''")
papers_l2 = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT paper_id) FROM paragraphs WHERE section_level3 IS NOT NULL AND section_level3 != ''")
papers_l3 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM paragraphs WHERE section_level1 IS NOT NULL AND section_level1 != ''")
l1_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM paragraphs WHERE section_level2 IS NOT NULL AND section_level2 != ''")
l2_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM paragraphs WHERE section_level3 IS NOT NULL AND section_level3 != ''")
l3_count = cur.fetchone()[0]
print(f"  L1 sections: {l1_count} (papers: {papers_l1})")
print(f"  L2 sections: {l2_count} (papers: {papers_l2})")
print(f"  L3 sections: {l3_count} (papers: {papers_l3})")

# ── 4. Citation DOI resolution ───────────────────────────────────────────
print("\n📊 4. Citation DOI Resolution")
print("-" * 50)
cur.execute("SELECT COUNT(*) FROM citations")
total_cites = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM citations WHERE doi IS NOT NULL AND doi != ''")
with_doi = cur.fetchone()[0]
print(f"  Total citations:   {total_cites}")
print(f"  With DOI:          {with_doi} ({with_doi/total_cites*100:.1f}%)")

# ── 5. Per-paper stats ────────────────────────────────────────────────────
print("\n📊 5. Per-Paper Paragraph Distribution")
print("-" * 50)
cur.execute("""
    SELECT p.title, COUNT(par.para_id) as n_paras
    FROM papers p
    LEFT JOIN paragraphs par ON p.paper_id = par.paper_id
    GROUP BY p.paper_id
    ORDER BY n_paras DESC
    LIMIT 10
""")
print("  Top 10 by paragraph count:")
for row in cur.fetchall():
    print(f"    {row['n_paras']:5d}  {row['title'][:60]}")

print("\n  Bottom 5 by paragraph count:")
cur.execute("""
    SELECT p.title, COUNT(par.para_id) as n_paras
    FROM papers p
    LEFT JOIN paragraphs par ON p.paper_id = par.paper_id
    GROUP BY p.paper_id
    ORDER BY n_paras ASC
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"    {row['n_paras']:5d}  {row['title'][:60]}")

# ── 6. Sample paragraphs from a Nature paper ──────────────────────────────
print("\n📊 6. Sample Paragraphs (Nature Communications paper)")
print("-" * 50)
cur.execute("""
    SELECT par.text, par.section_level1
    FROM paragraphs par
    JOIN papers p ON par.paper_id = p.paper_id
    WHERE p.filename LIKE '%s41467%'
    AND par.section_level1 IS NOT NULL AND par.section_level1 != ''
    AND par.text != par.section_level1
    LIMIT 8
""")
for row in cur.fetchall():
    text = row["text"][:120].replace("\n", " ")
    print(f"  [{row['section_level1'][:40]}]")
    print(f"    {text}...")
    print()

# ── 7. Table extraction ──────────────────────────────────────────────────
print("\n📊 7. Table Quality")
print("-" * 50)
cur.execute("SELECT COUNT(*) FROM tables")
total_tables = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM tables WHERE caption IS NOT NULL AND caption != ''")
tables_with_caption = cur.fetchone()[0]
print(f"  Total tables:      {total_tables}")
print(f"  With caption:      {tables_with_caption} ({tables_with_caption/total_tables*100:.1f}%)")

# ── 8. Papers by journal ──────────────────────────────────────────────────
print("\n📊 8. Papers by Journal")
print("-" * 50)
cur.execute("""
    SELECT journal, COUNT(*) as n
    FROM papers
    WHERE journal IS NOT NULL AND journal != ''
    GROUP BY journal
    ORDER BY n DESC
    LIMIT 15
""")
for row in cur.fetchall():
    print(f"  {row['n']:3d}  {row['journal'][:60]}")

conn.close()
print("\n" + "=" * 70)
print("✅ Quality analysis complete!")
print("=" * 70)
