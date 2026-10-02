"""
Extract figure captions from paragraphs.
V20.1 - Post-processing script to find figure caption text in paragraphs
and store them in a dedicated table for better RAG retrieval.
"""
import sqlite3
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "research.db"

# Regex to match figure captions: "Fig. 1." or "Figure 2." or "Fig 3:"
CAPTION_RE = re.compile(
    r'^(Fig(?:ure)?\.?\s*(\d+[a-z]?))[\.\:\s—\-]+\s*(.+)',
    re.IGNORECASE
)

def extract_captions():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Create figure_captions table if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS figure_captions (
            caption_id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL,
            fig_label TEXT NOT NULL,
            fig_number TEXT,
            caption_text TEXT NOT NULL,
            FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_captions_paper ON figure_captions(paper_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_captions_label ON figure_captions(fig_label)")

    # Clear existing
    cur.execute("DELETE FROM figure_captions")

    # Get all paragraphs
    cur.execute("SELECT para_id, paper_id, text FROM paragraphs")
    rows = cur.fetchall()

    count = 0
    for para_id, paper_id, text in rows:
        if not text or len(text) < 20:
            continue
        match = CAPTION_RE.match(text.strip())
        if match:
            fig_label = match.group(1).strip()
            fig_number = match.group(2)
            caption_text = match.group(0).strip()
            caption_id = f"cap_{paper_id[:20]}_{fig_number}"
            cur.execute("""
                INSERT OR REPLACE INTO figure_captions
                (caption_id, paper_id, fig_label, fig_number, caption_text)
                VALUES (?, ?, ?, ?, ?)
            """, (caption_id, paper_id, fig_label, fig_number, caption_text))
            count += 1

    conn.commit()

    # Stats
    cur.execute("SELECT COUNT(*) FROM figure_captions")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT paper_id) FROM figure_captions")
    papers_with_captions = cur.fetchone()[0]

    print(f"✅ Extracted {total} figure captions from {papers_with_captions} papers")

    # Show sample
    cur.execute("""
        SELECT p.title, fc.fig_label, fc.caption_text
        FROM figure_captions fc
        JOIN papers p ON fc.paper_id = p.paper_id
        LIMIT 5
    """)
    print("\nSample captions:")
    for title, label, text in cur.fetchall():
        print(f"  [{label}] {title[:40]}: {text[:80]}...")

    conn.close()

if __name__ == "__main__":
    extract_captions()
