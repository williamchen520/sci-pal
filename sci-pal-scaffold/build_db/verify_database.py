"""
Verify Sci-Pal Database
V18.0 - Comprehensive database verification with hierarchy check + suspicious-title scan
"""
import sqlite3
from pathlib import Path

project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "research.db"
images_dir = project_root / "images"


def verify_database():
    print("=" * 70)
    print("🔍 Sci-Pal Database Verification - V18.0")
    print("=" * 70)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # ============================================================
    # 1. Basic stats
    # ============================================================
    print("\n📊 1. Basic Statistics")
    print("-" * 50)

    tables = ["papers", "paragraphs", "figures", "tables", "citations", "paper_index", "cross_paper_index"]
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table:20s}: {count:6d} rows")

    # ============================================================
    # 2. Image file verification
    # ============================================================
    print("\n🖼️  2. Image File Verification")
    print("-" * 50)
    
    # Count figures with file_path
    cur.execute("SELECT COUNT(*) FROM figures WHERE file_path IS NOT NULL AND file_path != ''")
    figs_with_path = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM figures WHERE file_path IS NULL OR file_path = ''")
    figs_no_path = cur.fetchone()[0]
    
    print(f"  Figures with file_path: {figs_with_path}")
    print(f"  Figures without file_path: {figs_no_path}")
    
    # Check actual files on disk
    if images_dir.exists():
        actual_files = list(images_dir.glob("*.png"))
        print(f"  Actual PNG files on disk: {len(actual_files)}")
        
        # Verify file_path entries point to real files
        cur.execute("SELECT file_path FROM figures WHERE file_path IS NOT NULL AND file_path != ''")
        db_paths = cur.fetchall()
        missing = 0
        for (fp,) in db_paths:
            full_path = project_root / fp
            if not full_path.exists():
                missing += 1
        print(f"  DB entries pointing to missing files: {missing}")
        
        # Show sample of actual files
        print(f"\n  Sample image files (first 5):")
        for f in actual_files[:5]:
            size_kb = f.stat().st_size / 1024
            print(f"    {f.name} ({size_kb:.1f} KB)")
    else:
        print(f"  ❌ images/ directory does not exist!")

    # ============================================================
    # 3. Section name distribution
    # ============================================================
    print("\n📂 3. Section Name Distribution (top 10 level-1 sections)")
    print("-" * 50)
    cur.execute("""
        SELECT section_level1, COUNT(*) as count
        FROM paragraphs
        WHERE section_level1 IS NOT NULL AND section_level1 != ''
        GROUP BY section_level1
        ORDER BY count DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        section, count = row
        print(f"  {count:4d}  {section}")

    # ============================================================
    # 3b. Section hierarchy stats
    # ============================================================
    print("\n🏗️  3b. Section Hierarchy Stats")
    print("-" * 50)
    
    # How many papers have L2/L3 sections?
    cur.execute("""
        SELECT 
            COUNT(DISTINCT paper_id) as total_papers,
            COUNT(DISTINCT CASE WHEN section_level2 IS NOT NULL AND section_level2 != '' THEN paper_id END) as papers_with_l2,
            COUNT(DISTINCT CASE WHEN section_level3 IS NOT NULL AND section_level3 != '' THEN paper_id END) as papers_with_l3
        FROM paragraphs
    """)
    row = cur.fetchone()
    total, l2_count, l3_count = row
    print(f"  Total papers: {total}")
    print(f"  Papers with L2 sections: {l2_count} ({l2_count*100//total}%)")
    print(f"  Papers with L3 sections: {l3_count} ({l3_count*100//total}%)")
    
    # Show sample hierarchy from one paper
    print("\n  Sample hierarchy (first paper with L3):")
    cur.execute("""
        SELECT DISTINCT section_level1, section_level2, section_level3
        FROM paragraphs
        WHERE section_level3 IS NOT NULL AND section_level3 != ''
        LIMIT 15
    """)
    rows = cur.fetchall()
    for s1, s2, s3 in rows:
        print(f"    L1: {s1[:40] if s1 else 'None'}")
        print(f"      L2: {s2[:40] if s2 else 'None'}")
        print(f"        L3: {s3[:40] if s3 else 'None'}")

    # ============================================================
    # 4. Sample papers with titles
    # ============================================================
    print("\n📄 4. Sample Papers (first 5)")
    print("-" * 50)
    cur.execute("SELECT paper_id, title, doi, total_paragraphs FROM papers LIMIT 5")
    for row in cur.fetchall():
        paper_id, title, doi, paras = row
        title_short = (title[:50] + "...") if title and len(title) > 50 else (title or "No title")
        print(f"  {paper_id[:30]}...")
        print(f"    Title: {title_short}")
        print(f"    DOI: {doi or 'N/A'}")
        print(f"    Paragraphs: {paras}")
        print()

    # ============================================================
    # 5. Sample paragraphs with hierarchy
    # ============================================================
    print("📝 5. Sample Paragraphs (first 5 of first paper)")
    print("-" * 50)
    cur.execute("""
        SELECT p.para_id, p.section_level1, p.section_level2, substr(p.text, 1, 60)
        FROM paragraphs p
        JOIN papers p2 ON p.paper_id = p2.paper_id
        LIMIT 5
    """)
    for row in cur.fetchall():
        para_id, s1, s2, text = row
        print(f"  [{s1 or 'No section'}]")
        if s2:
            print(f"    [{s2}]")
        print(f"    {text}...")
        print()

    # ============================================================
    # 6. Sample figures with file paths
    # ============================================================
    print("🖼️  6. Sample Figures (first 5 with file paths)")
    print("-" * 50)
    cur.execute("""
        SELECT f.fig_number, substr(f.caption, 1, 60), f.file_path, p.filename
        FROM figures f
        JOIN papers p ON f.paper_id = p.paper_id
        WHERE f.file_path IS NOT NULL AND f.file_path != ''
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            fig_num, caption, file_path, filename = row
            print(f"  {fig_num}: {(caption or 'No caption')[:50]}...")
            print(f"    File: {file_path}")
            print()
    else:
        print("  (No figures with file paths found)")

    # ============================================================
    # 7. Cross-paper links
    # ============================================================
    print("🔗 7. Cross-Paper Links")
    print("-" * 50)
    cur.execute("""
        SELECT p1.title, p2.title, cpi.confidence
        FROM cross_paper_index cpi
        JOIN papers p1 ON cpi.source_paper_id = p1.paper_id
        JOIN papers p2 ON cpi.target_paper_id = p2.paper_id
        ORDER BY cpi.confidence DESC
    """)
    links = cur.fetchall()
    print(f"  Total links: {len(links)}")
    print()
    for row in links:
        source_title, target_title, confidence = row
        s_short = (source_title[:30] + "...") if source_title and len(source_title) > 30 else (source_title or "Unknown")
        t_short = (target_title[:30] + "...") if target_title and len(target_title) > 30 else (target_title or "Unknown")
        print(f"  [{confidence:.0%}]")
        print(f"    {s_short}")
        print(f"      → cites → {t_short}")
        print()

    # ============================================================
    # 8. All papers (filename → title)
    # ============================================================
    print("\n📋 8. All Papers (filename → title)")
    print("-" * 50)
    cur.execute("""
        SELECT filename, title FROM papers
        ORDER BY filename
    """)
    all_papers = cur.fetchall()
    for row in all_papers:
        filename, title = row
        title_short = (title[:60] + "...") if title and len(title) > 60 else (title or "❌ No title")
        print(f"  {filename[:40]:40s} → {title_short}")

    # ============================================================
    # 9. Papers with no title
    # ============================================================
    print("\n❌ 9. Papers with No Title")
    print("-" * 50)
    cur.execute("""
        SELECT filename, paper_id FROM papers
        WHERE title IS NULL OR title = '' OR title = 'No title'
    """)
    no_title_papers = cur.fetchall()
    if no_title_papers:
        for row in no_title_papers:
            filename, paper_id = row
            print(f"  {filename}")
    else:
        print("  ✅ All papers have titles!")

    # ============================================================
    # 9b. Suspicious titles (V18.0) — all-caps headers, consortium names, truncated
    # ============================================================
    print("\n🔍 9b. Suspicious-Looking Titles")
    print("-" * 50)

    CONSORTIUM_SUFFIXES = (
        " research team", " study group", " study team", " consortium",
        " collaboration", " network", " initiative", " project",
        " group", " working group",
    )

    cur.execute("SELECT filename, title FROM papers WHERE title IS NOT NULL AND title != ''")
    suspicious_found = 0
    for filename, title in cur.fetchall():
        flags = []
        if title.endswith("(") and title.count("(") > title.count(")"):
            flags.append("unbalanced_paren")
        t_lower = title.lower().rstrip(".")
        for suffix in CONSORTIUM_SUFFIXES:
            if t_lower.endswith(suffix) and len(title.split()) <= 8:
                flags.append(f"consortium:{suffix.strip()}")
                break
        letters = [c for c in title if c.isalpha()]
        if letters:
            upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            if upper_ratio > 0.85 and len(title.split()) <= 8:
                flags.append(f"all_caps({upper_ratio:.0%})")
        if flags:
            suspicious_found += 1
            print(f"  ⚠️  {filename[:45]:45s} | {title[:50]} | flags: {', '.join(flags)}")

    if suspicious_found == 0:
        print("  ✅ No suspicious titles detected.")

    # ============================================================
    # 10. Most figures per paper (top 5)
    # ============================================================
    print("\n🏆 10. Most Figures per Paper (top 5)")
    print("-" * 50)
    cur.execute("""
        SELECT p.title, p.filename, COUNT(f.fig_id) as fig_count
        FROM papers p
        JOIN figures f ON p.paper_id = f.paper_id
        GROUP BY p.paper_id
        ORDER BY fig_count DESC
        LIMIT 5
    """)
    for row in cur.fetchall():
        title, filename, count = row
        title_short = (title[:35] + "...") if title and len(title) > 35 else "No title"
        file_short = filename[:35]
        print(f"  {count:2d} figures: {title_short}")
        print(f"           File: {file_short}")

    # ============================================================
    # 11. Citation stats
    # ============================================================
    print("\n📚 11. Citation Stats")
    print("-" * 50)
    cur.execute("SELECT COUNT(*) FROM citations")
    total_cites = cur.fetchone()[0]
    print(f"  Total citation entries: {total_cites}")
    
    cur.execute("SELECT COUNT(*) FROM citations WHERE doi IS NOT NULL AND doi != ''")
    cites_with_doi = cur.fetchone()[0]
    print(f"  Citations with DOI: {cites_with_doi}")

    conn.close()
    print("\n" + "=" * 70)
    print("✅ Verification complete!")
    print("=" * 70)


if __name__ == "__main__":
    verify_database()
