"""
摘要库检索：vector + FTS，跟全文库并列。
V30.0 - Abstract search layer
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
import chromadb

PROJECT_ROOT = Path(__file__).parent.parent.parent
ABSTRACT_DB_PATH = PROJECT_ROOT / "data" / "abstracts.db"
ABSTRACT_CHROMA_PATH = PROJECT_ROOT / "data" / "chroma_abstracts"

EMBEDDING_MODEL = r"D:\models\models\BAAI--bge-base-en-v1.5"  # V31.26: 从 all-mpnet-base-v2 改成 bge-base-en-v1.5


class AbstractSearch:
    """摘要库检索：跟全文库并列，先查全文库，再查摘要库。"""
    
    def __init__(self):
        self.db_path = ABSTRACT_DB_PATH
        self.chroma_path = ABSTRACT_CHROMA_PATH
        
        # 加载 embedding 模型
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        
        # 加载 Chroma 客户端
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_path))
        self.collection = self.chroma_client.get_or_create_collection(name="abstracts")
    
    def vector_search(self, query: str, top_k: int = 10) -> List[Dict]:
        """向量搜索摘要库"""
        query_embedding = self.model.encode([query])
        
        results = self.collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=top_k,
        )
        
        hits = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]
        
        for i in range(len(ids)):
            hits.append({
                "pmid": metadatas[i].get("pmid", ""),
                "doi": metadatas[i].get("doi", ""),
                "title": metadatas[i].get("title", ""),
                "abstract": documents[i],
                "authors": metadatas[i].get("authors", ""),
                "journal": metadatas[i].get("journal", ""),
                "year": metadatas[i].get("year", ""),
                "topic": metadatas[i].get("topic", ""),
                "source": "pubmed_abstract",  # 标注是摘要
                "score": 1 - distances[i] if distances else 0,
            })
        
        return hits
    
    def fts_search(self, query: str, top_k: int = 10) -> List[Dict]:
        """FTS 搜索摘要库"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        # FTS 表只有 pmid, title, abstract, authors, journal, topic
        # 先从 FTS 表查 pmid，再从 papers 表关联查 doi, year
        sql = """
            SELECT p.pmid, p.doi, p.title, p.abstract, p.authors, p.journal, p.year, p.topic
            FROM papers_fts f
            JOIN papers p ON f.pmid = p.pmid
            WHERE papers_fts MATCH ?
            LIMIT ?
        """
        
        try:
            rows = conn.execute(sql, (query, top_k)).fetchall()
        except Exception as e:
            print(f"  ⚠️  摘要 FTS 搜索失败: {e}")
            conn.close()
            return []
        
        hits = []
        for row in rows:
            hits.append({
                "pmid": row["pmid"],
                "doi": row["doi"],
                "title": row["title"],
                "abstract": row["abstract"],
                "authors": row["authors"],
                "journal": row["journal"],
                "year": row["year"],
                "topic": row["topic"],
                "source": "pubmed_abstract",  # 标注是摘要
                "score": 1.0,
            })
        
        conn.close()
        return hits
    
    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """混合搜索：向量 + FTS，RRF 融合"""
        vector_hits = self.vector_search(query, top_k * 2)
        fts_hits = self.fts_search(query, top_k * 2)
        
        # 简单的 RRF 融合
        rrf_k = 60
        scores = {}
        
        for rank, hit in enumerate(vector_hits):
            key = hit["pmid"]
            scores[key] = scores.get(key, 0) + 1 / (rrf_k + rank + 1)
        
        for rank, hit in enumerate(fts_hits):
            key = hit["pmid"]
            scores[key] = scores.get(key, 0) + 1 / (rrf_k + rank + 1)
        
        # 按分数排序
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
        
        # 合并结果
        all_hits = {}
        for hit in vector_hits + fts_hits:
            key = hit["pmid"]
            if key not in all_hits or hit.get("score", 0) > all_hits[key].get("score", 0):
                all_hits[key] = hit
        
        # 按排序结果取 top_k
        results = []
        for key in sorted_keys[:top_k]:
            if key in all_hits:
                hit = all_hits[key]
                hit["score"] = scores[key]
                results.append(hit)
        
        return results


if __name__ == "__main__":
    # 测试
    searcher = AbstractSearch()
    results = searcher.search("STAT1 interferon signaling", top_k=5)
    
    print("=" * 60)
    print("🔍 摘要库检索测试")
    print("=" * 60)
    
    for i, hit in enumerate(results):
        print(f"\n#{i+1} (score: {hit['score']:.4f})")
        print(f"  标题: {hit['title'][:80]}...")
        print(f"  期刊: {hit['journal']} ({hit['year']})")
        print(f"  来源: {hit['source']}")
