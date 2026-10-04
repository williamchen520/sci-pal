"""Build vector index with ChromaDB"""
import sqlite3
import chromadb
from sentence_transformers import SentenceTransformer


def build_vector_index():
    db_path = 'data/research.db'
    chroma_path = 'data/chroma'
    
    # Load model
    print("Loading embedding model...")
    model = SentenceTransformer('all-mpnet-base-v2')
    
    # Connect to Chroma
    print("Connecting to ChromaDB...")
    client = chromadb.PersistentClient(path=chroma_path)
    
    # Create or get collection
    collection = client.get_or_create_collection(
        name="sci_pal_sentences",
        metadata={"hnsw:space": "cosine"}
    )
    
    # Note: don't clear old data, just add new data
    # If you want to clear, delete the collection and recreate
    
    # Load sentences from database
    print("Loading sentences from database...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("""
        SELECT s.sentence_id, s.text, s.para_id, p.paper_id, p.parse_engine
        FROM sentences s
        JOIN paragraphs p ON s.para_id = p.para_id
    """)
    
    sentences = c.fetchall()
    print(f"Total sentences: {len(sentences)}")
    
    # Batch process
    batch_size = 1000
    total_batches = (len(sentences) + batch_size - 1) // batch_size
    
    print(f"Processing {total_batches} batches...")
    
    for i in range(total_batches):
        start = i * batch_size
        end = min(start + batch_size, len(sentences))
        batch = sentences[start:end]
        
        # Prepare data
        ids = [row[0] for row in batch]
        texts = [row[1] for row in batch]
        metadatas = [
            {
                "para_id": row[2],
                "paper_id": row[3],
                "parse_engine": row[4]
            }
            for row in batch
        ]
        
        # Compute embeddings
        embeddings = model.encode(texts, show_progress_bar=False)
        
        # Add to Chroma
        collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )
        
        print(f"  Batch {i+1}/{total_batches}: {end}/{len(sentences)} sentences")
    
    conn.close()
    
    # Verify
    count = collection.count()
    print("\n" + "="*80)
    print(f"✅ Vector index built!")
    print(f"  Total vectors in Chroma: {count}")
    print("="*80)


if __name__ == "__main__":
    build_vector_index()
