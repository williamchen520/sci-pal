#!/usr/bin/env python3
"""
摘要数据库建索引脚本 V1.0

从 abstracts_xml/ 目录下的 JSON 文件建：
1. SQLite 数据库（data/abstracts.db）
2. FTS5 全文索引
3. 向量索引（用 all-mpnet-base-v2）

使用方法：
  python build_abstracts_db.py
"""

import json
import sqlite3
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

# 路径配置
PROJECT_ROOT = Path(__file__).parent
ABSTRACTS_DIR = PROJECT_ROOT / "abstracts_xml"
DB_PATH = PROJECT_ROOT / "data" / "abstracts.db"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_abstracts"

# 模型配置
# V32.7: 跟主程序保持一致，用 BAAI/bge-base-en-v1.5，支持本地模型路径
# 优先级：环境变量 ABSTRACT_EMBEDDING_MODEL > 本地路径 > 默认模型名
import os
EMBEDDING_MODEL = os.environ.get(
    "ABSTRACT_EMBEDDING_MODEL",
    os.environ.get("SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5"),
)
# 如果本地路径不存在，回退到模型名（会自动下载）
if not os.path.exists(EMBEDDING_MODEL):
    EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
    print(f"⚠️  本地模型路径不存在，回退到模型名: {EMBEDDING_MODEL}")


def create_database():
    """建 SQLite 数据库和表"""
    print("=" * 60)
    print("🗄️  建摘要数据库")
    print("=" * 60)
    
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # 建 papers 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pmid TEXT UNIQUE,
            doi TEXT,
            title TEXT,
            abstract TEXT,
            authors TEXT,
            journal TEXT,
            year INTEGER,
            topic TEXT,
            source TEXT DEFAULT 'pubmed_abstract'
        )
    """)
    
    # 建 FTS 表
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
            pmid UNINDEXED,
            title,
            abstract,
            authors,
            journal,
            topic UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 2'
        )
    """)
    
    conn.commit()
    return conn


def load_json_files():
    """加载所有 JSON 文件"""
    print("\n📥 加载 JSON 文件...")
    
    all_papers = []
    
    for json_file in ABSTRACTS_DIR.glob("*.json"):
        topic = json_file.stem.replace("_", " ")
        print(f"  加载: {json_file.name} (主题: {topic})")
        
        with open(json_file, "r", encoding="utf-8") as f:
            papers = json.load(f)
        
        for paper in papers:
            paper["topic"] = topic
            all_papers.append(paper)
    
    print(f"\n✅ 总共加载了 {len(all_papers)} 篇摘要")
    return all_papers


def insert_papers(conn, papers):
    """插入数据到数据库"""
    print("\n📝 插入数据到数据库...")
    
    batch_size = 1000
    for i in range(0, len(papers), batch_size):
        batch = papers[i:i+batch_size]
        
        for paper in batch:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO papers 
                    (pmid, doi, title, abstract, authors, journal, year, topic)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    paper.get("pmid", ""),
                    paper.get("doi", ""),
                    paper.get("title", ""),
                    paper.get("abstract", ""),
                    paper.get("authors", ""),
                    paper.get("journal", ""),
                    paper.get("year"),
                    paper.get("topic", ""),
                ))
            except Exception as e:
                print(f"  ⚠️  插入失败: {e}")
        
        conn.commit()
        print(f"  已插入 {min(i+batch_size, len(papers))}/{len(papers)}")


def build_fts(conn):
    """建 FTS 索引"""
    print("\n🔍 建 FTS 索引...")
    
    # 清空 FTS 表
    conn.execute("DELETE FROM papers_fts")
    conn.commit()
    
    # 从 papers 表填充 FTS
    rows = conn.execute("""
        SELECT pmid, title, abstract, authors, journal, topic
        FROM papers
        WHERE abstract IS NOT NULL AND length(abstract) > 10
    """).fetchall()
    
    print(f"  索引 {len(rows)} 篇摘要...")
    
    batch_size = 1000
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        
        conn.executemany("""
            INSERT INTO papers_fts (pmid, title, abstract, authors, journal, topic)
            VALUES (?, ?, ?, ?, ?, ?)
        """, batch)
        
        conn.commit()
        print(f"  已索引 {min(i+batch_size, len(rows))}/{len(rows)}")


def build_embeddings(papers):
    """建向量索引"""
    print("\n🤖 建向量索引...")
    
    # 加载模型
    print(f"  加载模型: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    
    # 准备文本
    texts = []
    metadatas = []
    ids = []
    
    for i, paper in enumerate(papers):
        text = f"{paper.get('title', '')}\n\n{paper.get('abstract', '')}"
        texts.append(text)
        metadatas.append({
            "pmid": paper.get("pmid", ""),
            "doi": paper.get("doi", ""),
            "title": paper.get("title", ""),
            "authors": paper.get("authors", ""),
            "journal": paper.get("journal", ""),
            "year": paper.get("year"),
            "topic": paper.get("topic", ""),
            "source": "pubmed_abstract",
        })
        ids.append(f"abstract_{paper.get('pmid', i)}")
    
    # 生成向量
    print(f"  生成 {len(texts)} 个向量...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    
    # 保存到 Chroma
    print(f"  保存到 Chroma: {CHROMA_DIR}")
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        collection = client.get_or_create_collection(name="abstracts")
        
        # 批量插入
        batch_size = 1000
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i:i+batch_size]
            batch_embeddings = embeddings[i:i+batch_size].tolist()
            batch_metadatas = metadatas[i:i+batch_size]
            batch_documents = texts[i:i+batch_size]
            
            collection.add(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents,
            )
        
        print(f"  ✅ 已保存 {len(ids)} 个向量到 Chroma")
    except Exception as e:
        print(f"  ⚠️  保存到 Chroma 失败: {e}")
        # 降级：保存到 numpy 文件
        np.save(CHROMA_DIR / "embeddings.npy", embeddings)
        with open(CHROMA_DIR / "metadatas.json", "w", encoding="utf-8") as f:
            json.dump(metadatas, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 已保存向量到 numpy 文件")


def main():
    print("=" * 60)
    print("📊 摘要数据库建索引脚本 V1.0")
    print("=" * 60)
    
    # 1. 建数据库
    conn = create_database()
    
    # 2. 加载 JSON 文件
    papers = load_json_files()
    
    # 3. 插入数据
    insert_papers(conn, papers)
    
    # 4. 建 FTS 索引
    build_fts(conn)
    
    # 5. 建向量索引
    build_embeddings(papers)
    
    # 关闭连接
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)
    print(f"  数据库: {DB_PATH}")
    print(f"  FTS 索引: 已建")
    print(f"  向量索引: {CHROMA_DIR}")
    print(f"  总篇数: {len(papers)}")


if __name__ == "__main__":
    main()
