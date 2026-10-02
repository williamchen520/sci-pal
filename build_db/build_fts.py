"""
Build FTS5 full-text search index for paragraphs.
V21.0 - Full-text search layer
"""
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"


def build_fts():
    """Create FTS5 virtual table and populate it."""
    print("=" * 60)
    print("🔍 Building Full-Text Search Index (FTS5)")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Drop existing FTS table if any
    conn.execute("DROP TABLE IF EXISTS paragraphs_fts")
    conn.commit()

    # Create FTS5 virtual table
    print("\n📋 Creating FTS5 virtual table...")
    conn.execute("""
        CREATE VIRTUAL TABLE paragraphs_fts USING fts5(
            para_id UNINDEXED,
            paper_id UNINDEXED,
            section_l1,
            section_l2,
            text,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    conn.commit()

    # Populate from paragraphs
    print("📥 Populating FTS index...")
    rows = conn.execute("""
        SELECT para_id, paper_id, section_level1, section_level2, text
        FROM paragraphs
        WHERE text IS NOT NULL AND length(text) > 10
    """).fetchall()

    print(f"   Indexing {len(rows)} paragraphs...")

    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        conn.executemany("""
            INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text)
            VALUES (?, ?, ?, ?, ?)
        """, [(
            r["para_id"],
            r["paper_id"],
            r["section_level1"] or "",
            r["section_level2"] or "",
            r["text"]
        ) for r in batch])
        conn.commit()
        print(f"   [{min(i+batch_size, len(rows))}/{len(rows)}] indexed...")

    # Also index paper titles
    conn.execute("DROP TABLE IF EXISTS papers_fts")
    conn.execute("""
        CREATE VIRTUAL TABLE papers_fts USING fts5(
            paper_id UNINDEXED,
            title,
            authors,
            journal,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    conn.commit()

    papers = conn.execute("SELECT paper_id, title, authors, journal FROM papers").fetchall()
    conn.executemany("""
        INSERT INTO papers_fts (paper_id, title, authors, journal)
        VALUES (?, ?, ?, ?)
    """, [(p["paper_id"], p["title"] or "", p["authors"] or "", p["journal"] or "") for p in papers])
    conn.commit()
    print(f"   Indexed {len(papers)} papers")

    conn.close()
    print("\n✅ FTS5 index built successfully!")


if __name__ == "__main__":
    build_fts()
