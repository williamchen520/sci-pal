"""
Build 800-token chunks from paragraphs.
V24.1 - Section-aware greedy chunking

Reads all paragraphs from SQLite, groups by (paper_id, section_level1),
packs into ~800-token chunks, writes to a `chunks` table, and builds
a Chroma `chunks` collection for vector retrieval.

Usage:
  python -m build_db.build_chunks                  # dry-run (stats only)
  python -m build_db.build_chunks --apply          # write to DB + Chroma
  python -m build_db.build_chunks --max-tokens 512 # custom chunk size
"""
import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "research.db"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"


def get_chunks_table_ddl() -> str:
    return """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id        TEXT PRIMARY KEY,
        paper_id        TEXT NOT NULL,
        section_level1  TEXT,
        section_level2  TEXT,
        start_para_id   TEXT,
        end_para_id     TEXT,
        text            TEXT NOT NULL,
        token_count     INTEGER DEFAULT 0,
        page            INTEGER,
        start_sequence  INTEGER DEFAULT 0,
        end_sequence    INTEGER DEFAULT 0,
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_paper ON chunks(paper_id);
    CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_level1);
    """


def main():
    parser = argparse.ArgumentParser(description="Build 800-token chunks")
    parser.add_argument("--apply", action="store_true", help="Write to DB + Chroma")
    parser.add_argument("--max-tokens", type=int, default=800, help="Max tokens per chunk")
    parser.add_argument("--overlap", type=int, default=50, help="Overlap tokens between chunks")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print("=" * 60)
    print(f"📦 Chunk Builder (V24.1) — {mode}")
    print("=" * 60)
    print(f"  max_tokens={args.max_tokens}, overlap={args.overlap}")

    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Read all paragraphs
    print("\n── Reading paragraphs ──")
    paras = conn.execute("""
        SELECT para_id, paper_id, section_level1, section_level2,
               text, sequence, page
        FROM paragraphs
        WHERE text IS NOT NULL AND trim(text) != ''
        ORDER BY paper_id, section_level1, sequence
    """).fetchall()
    print(f"  {len(paras)} non-empty paragraphs")

    # Chunk
    from services.search.chunker import Chunker
    chunker = Chunker(max_tokens=args.max_tokens, overlap=args.overlap)

    para_dicts = [dict(p) for p in paras]
    chunks = chunker.chunk_paragraphs(para_dicts)

    # Stats
    token_counts = [c["token_count"] for c in chunks]
    avg_tokens = sum(token_counts) / len(chunks) if chunks else 0
    sections = set(c["section_level1"] for c in chunks)
    papers = set(c["paper_id"] for c in chunks)

    print(f"\n── Chunk statistics ──")
    print(f"  Total chunks:     {len(chunks)}")
    print(f"  Papers covered:   {len(papers)}")
    print(f"  Sections:         {len(sections)}")
    print(f"  Avg tokens/chunk: {avg_tokens:.0f}")
    print(f"  Min tokens:       {min(token_counts) if token_counts else 0}")
    print(f"  Max tokens:       {max(token_counts) if token_counts else 0}")

    # Token size distribution
    bins = [(0, 200), (200, 400), (400, 600), (600, 800), (800, 1000), (1000, 9999)]
    print(f"\n  Token distribution:")
    for lo, hi in bins:
        count = sum(1 for t in token_counts if lo <= t < hi)
        pct = 100 * count / len(chunks) if chunks else 0
        bar = "█" * int(pct / 2)
        print(f"    {lo:4d}-{hi:4d}: {count:5d} ({pct:5.1f}%) {bar}")

    if not args.apply:
        print(f"\n  💡 Dry-run complete. Run with --apply to write to DB + Chroma.")
        conn.close()
        return

    # Write to SQLite
    print(f"\n── Writing to SQLite ──")
    conn.executescript(get_chunks_table_ddl())
    conn.execute("DELETE FROM chunks")  # idempotent rebuild
    conn.executemany("""
        INSERT OR REPLACE INTO chunks
        (chunk_id, paper_id, section_level1, section_level2,
         start_para_id, end_para_id, text, token_count, page,
         start_sequence, end_sequence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        c["chunk_id"], c["paper_id"], c["section_level1"], c["section_level2"],
        c["start_para_id"], c["end_para_id"], c["text"], c["token_count"],
        c["page"], c["start_sequence"], c["end_sequence"]
    ) for c in chunks])
    conn.commit()
    print(f"  ✅ {len(chunks)} chunks written to chunks table")

    # Build Chroma chunks collection
    print(f"\n── Building Chroma chunks collection ──")
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        # Delete existing collection if present (idempotent rebuild)
        try:
            client.delete_collection("chunks")
        except Exception:
            pass
        collection = client.create_collection(
            name="chunks",
            metadata={"hnsw:space": "cosine"},
        )

        print("  Loading embedding model...")
        model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

        # Batch encode
        batch_size = 64
        total = len(chunks)
        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]
            ids = [c["chunk_id"] for c in batch]
            metadatas = [{
                "paper_id": c["paper_id"],
                "section_l1": c["section_level1"] or "",
                "section_l2": c["section_level2"] or "",
                "page": c["page"] or 0,
                "token_count": c["token_count"],
            } for c in batch]
            embeddings = model.encode(texts, show_progress_bar=False)
            collection.upsert(
                ids=ids,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
                documents=texts,
            )
            print(f"  Encoded {min(i + batch_size, total)}/{total} chunks")

        print(f"  ✅ Chroma chunks collection built: {collection.count()} vectors")
    except ImportError as e:
        print(f"  ⚠️  Skipping Chroma build (missing dependency: {e})")
        print(f"     Install with: pip install chromadb sentence-transformers")
    except Exception as e:
        print(f"  ⚠️  Chroma build failed: {e}")

    conn.close()
    print(f"\n✅ Build complete. {len(chunks)} chunks ready for retrieval.")


if __name__ == "__main__":
    main()
