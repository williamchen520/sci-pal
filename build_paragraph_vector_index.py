"""
Build Paragraph-level Vector Index
===================================
为 paragraphs 表建向量索引。

用法：
    python -m build_db.process.build_paragraph_vector_index
"""

import sqlite3
import chromadb
from sentence_transformers import SentenceTransformer


# 数据库路径
DB_PATH = "data/research.db"
CHROMA_PATH = "data/chroma"
EMBEDDING_MODEL = "all-mpnet-base-v2"
COLLECTION_NAME = "sci_pal_paragraphs"


def build_paragraph_vector_index():
    """建段落级向量索引"""
    print("=" * 60)
    print("Building Paragraph-level Vector Index")
    print("=" * 60)

    # 1. 加载模型
    print(f"\n[1/5] Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("  ✅ Model loaded")

    # 2. 连接 Chroma
    print(f"\n[2/5] Connecting to ChromaDB: {CHROMA_PATH}")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    print("  ✅ Connected")

    # 3. 删除旧 collection（如果存在）
    print(f"\n[3/5] Deleting old collection: {COLLECTION_NAME}")
    try:
        client.delete_collection(COLLECTION_NAME)
        print("  ✅ Old collection deleted")
    except:
        print("  ℹ️ No old collection")

    # 4. 创建新 collection
    print(f"\n[4/5] Creating new collection: {COLLECTION_NAME}")
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print("  ✅ Collection created")

    # 5. 读取 paragraphs 表，做 embedding，存入 Chroma
    print(f"\n[5/5] Building embeddings...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT para_id, paper_id, section_level1, section_level2, section_level3, text
        FROM paragraphs
    """)
    rows = cursor.fetchall()
    print(f"  Total paragraphs: {len(rows)}")

    # 批量 embedding
    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        
        ids = [row["para_id"] for row in batch]
        documents = [row["text"] for row in batch]
        metadatas = [
            {
                "paper_id": row["paper_id"] or "",
                "section_l1": row["section_level1"] or "",
                "section_l2": row["section_level2"] or "",
            }
            for row in batch
        ]

        # 做 embedding
        embeddings = model.encode(documents).tolist()

        # 存入 Chroma
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        print(f"  Processed {min(i+batch_size, len(rows))}/{len(rows)}")

    conn.close()

    print("\n" + "=" * 60)
    print("✅ Paragraph vector index built!")
    print("=" * 60)


if __name__ == "__main__":
    build_paragraph_vector_index()
