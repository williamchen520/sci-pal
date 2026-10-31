"""
Build vector embeddings for paragraphs using Chroma DB.
V21.0 - Embedding layer
"""
import os
import sqlite3
from pathlib import Path
import chromadb
from chromadb.config import Settings

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"

# Embedding model
EMBEDDING_MODEL = os.environ.get("SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")


def build_embeddings():
    """Generate embeddings for all paragraphs and store in Chroma."""
    print("=" * 60)
    print("🧠 Building Vector Embeddings")
    print("=" * 60)

    # Connect to SQLite
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all paragraphs
    print(f"\n📄 Loading paragraphs from {DB_PATH}...")
    rows = conn.execute("""
        SELECT para_id, paper_id, section_level1, section_level2, text, sequence
        FROM paragraphs
        ORDER BY paper_id, sequence
    """).fetchall()
    print(f"   Total paragraphs: {len(rows)}")

    # Initialize Chroma
    print(f"\n🗄️  Initializing Chroma at {CHROMA_PATH}...")
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Create or get collection
    collection = client.get_or_create_collection(
        name="paragraphs",
        metadata={"hnsw:space": "cosine"}
    )

    # Check if paragraphs already embedded
    existing = collection.count()
    skip_paragraphs = existing > 0
    if skip_paragraphs:
        print(f"   Already have {existing} paragraph embeddings, skipping paragraphs...")

    # Load embedding model (always needed; papers/figures/tables may still need it)
    print(f"\n🔤 Loading embedding model: {EMBEDDING_MODEL}...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)

    batch_size = 64

    if not skip_paragraphs:
        # Prepare texts and metadata
        print(f"\n📝 Generating embeddings for {len(rows)} paragraphs...")
        all_ids = []
        all_texts = []
        all_metadatas = []

        for i, row in enumerate(rows):
            text = row["text"]
            if not text or len(text.strip()) < 10:
                continue

            all_ids.append(row["para_id"])
            all_texts.append(text)
            all_metadatas.append({
                "paper_id": row["paper_id"],
                "section_l1": row["section_level1"] or "",
                "section_l2": row["section_level2"] or "",
                "sequence": row["sequence"] or 0,
            })

        print(f"   Valid paragraphs: {len(all_texts)}")

        # Generate embeddings in batches
        total = len(all_texts)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_texts = all_texts[start:end]
            batch_ids = all_ids[start:end]
            batch_meta = all_metadatas[start:end]

            embeddings = model.encode(batch_texts, show_progress_bar=False)

            collection.add(
                ids=batch_ids,
                embeddings=embeddings.tolist(),
                documents=batch_texts,
                metadatas=batch_meta
            )

            if (start // batch_size) % 5 == 0:
                print(f"   [{end}/{total}] embedded...")

    # Also embed paper abstracts
    print(f"\n📝 Embedding paper abstracts...")
    papers = conn.execute("""
        SELECT paper_id, title, authors FROM papers
    """).fetchall()

    paper_ids = []
    paper_texts = []
    paper_metas = []

    for p in papers:
        if p["title"]:
            paper_ids.append(p["paper_id"])
            paper_texts.append(f"{p['title']}. {p['authors'] or ''}")
            paper_metas.append({"type": "paper"})

    if paper_ids:
        paper_collection = client.get_or_create_collection(
            name="papers",
            metadata={"hnsw:space": "cosine"}
        )
        if paper_collection.count() == 0:
            paper_embeddings = model.encode(paper_texts, show_progress_bar=False)
            paper_collection.add(
                ids=paper_ids,
                embeddings=paper_embeddings.tolist(),
                documents=paper_texts,
                metadatas=paper_metas
            )
            print(f"   Embedded {len(paper_ids)} papers")
        else:
            print(f"   Already have {paper_collection.count()} papers, skipping")
    else:
        paper_collection = None

    # Embed figure captions
    print(f"\n🖼️  Embedding figure captions...")
    figures = conn.execute("""
        SELECT fig_id, paper_id, fig_number, caption, file_path, page
        FROM figures WHERE caption IS NOT NULL AND length(caption) > 5
    """).fetchall()

    if figures:
        fig_collection = client.get_or_create_collection(
            name="figures",
            metadata={"hnsw:space": "cosine"}
        )
        if fig_collection.count() == 0:
            fig_ids, fig_texts, fig_metas = [], [], []
            for f in figures:
                fig_ids.append(f["fig_id"])
                # Caption text is what we search against
                fig_texts.append(f"{f['fig_number']}. {f['caption']}")
                fig_metas.append({
                    "paper_id": f["paper_id"],
                    "fig_number": f["fig_number"] or "",
                    "file_path": f["file_path"] or "",
                    "page": f["page"] or 0,
                })
            fig_embs = model.encode(fig_texts, show_progress_bar=False)
            # Add in batches
            for start in range(0, len(fig_ids), batch_size):
                end = min(start + batch_size, len(fig_ids))
                fig_collection.add(
                    ids=fig_ids[start:end],
                    embeddings=fig_embs[start:end].tolist(),
                    documents=fig_texts[start:end],
                    metadatas=fig_metas[start:end]
                )
            print(f"   Embedded {len(fig_ids)} figures")
        else:
            print(f"   Already have {fig_collection.count()} figures, skipping")
    else:
        fig_collection = None
        print("   No figure captions found")

    # Embed tables (caption + markdown content)
    print(f"\n📊 Embedding tables...")
    tables = conn.execute("""
        SELECT table_id, paper_id, table_number, caption, markdown, page
        FROM tables WHERE (caption IS NOT NULL AND length(caption) > 5)
           OR (markdown IS NOT NULL AND length(markdown) > 20)
    """).fetchall()

    if tables:
        table_collection = client.get_or_create_collection(
            name="tables",
            metadata={"hnsw:space": "cosine"}
        )
        if table_collection.count() == 0:
            tbl_ids, tbl_texts, tbl_metas = [], [], []
            for t in tables:
                # Combine caption with a truncated version of table content
                content = t["markdown"] or ""
                if len(content) > 1500:
                    content = content[:1500]
                tbl_ids.append(t["table_id"])
                tbl_texts.append(f"{t['table_number'] or 'Table'}. {t['caption'] or ''}\n{content}")
                tbl_metas.append({
                    "paper_id": t["paper_id"],
                    "table_number": t["table_number"] or "",
                    "page": t["page"] or 0,
                })
            tbl_embs = model.encode(tbl_texts, show_progress_bar=False)
            for start in range(0, len(tbl_ids), batch_size):
                end = min(start + batch_size, len(tbl_ids))
                table_collection.add(
                    ids=tbl_ids[start:end],
                    embeddings=tbl_embs[start:end].tolist(),
                    documents=tbl_texts[start:end],
                    metadatas=tbl_metas[start:end]
                )
            print(f"   Embedded {len(tbl_ids)} tables")
        else:
            print(f"   Already have {table_collection.count()} tables, skipping")
    else:
        table_collection = None
        print("   No tables found")

    conn.close()
    print(f"\n✅ Done! Embeddings stored in {CHROMA_PATH}")
    print(f"   Paragraphs: {collection.count()}")
    print(f"   Papers: {paper_collection.count() if paper_ids else 0}")
    print(f"   Figures: {fig_collection.count() if figures else 0}")
    print(f"   Tables: {table_collection.count() if tables else 0}")


if __name__ == "__main__":
    build_embeddings()
