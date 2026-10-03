"""
V31.30: 句子切分脚本

把段落和摘要切成句子，建 sentences 表，建正向索引。

ID 命名规则：
- research.db: sentence_id = {para_id}_sent_{3位序号}
- abstracts.db: sentence_id = {pmid}_sent_{3位序号}
"""

import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# 路径配置
RESEARCH_DB = PROJECT_ROOT / "data" / "research.db"
ABSTRACTS_DB = PROJECT_ROOT / "data" / "abstracts.db"


def split_into_sentences(text: str) -> list[str]:
    """把文本切成句子（按句号、问号、感叹号切）"""
    if not text:
        return []
    
    # 简单的句子切分：按句号、问号、感叹号切
    # 注意：要处理缩写（比如 Mr. Dr. 等），但是！先简单处理
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    # 过滤空句子
    sentences = [s.strip() for s in sentences if s.strip()]
    
    return sentences


def build_sentences_for_research_db():
    """为 research.db 建 sentences 表"""
    print("\n" + "=" * 60)
    print("📝 为 research.db 建 sentences 表")
    print("=" * 60)
    
    conn = sqlite3.connect(str(RESEARCH_DB))
    
    # 建 sentences 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentences (
            sentence_id TEXT PRIMARY KEY,
            para_id TEXT NOT NULL,
            paper_id TEXT NOT NULL,
            text TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            FOREIGN KEY (para_id) REFERENCES paragraphs(para_id),
            FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
        )
    """)
    
    # 建正向索引：para_id → 句子
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentences_para 
        ON sentences(para_id, sequence)
    """)
    
    # 建反向索引：paper_id → 句子
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentences_paper 
        ON sentences(paper_id, sequence)
    """)
    
    # 读所有段落
    rows = conn.execute("""
        SELECT para_id, paper_id, text
        FROM paragraphs
    """).fetchall()
    
    print(f"\n📥 读了 {len(rows)} 个段落")
    
    # 切分句子
    all_sentences = []
    for para_id, paper_id, text in rows:
        sentences = split_into_sentences(text)
        
        for i, sent in enumerate(sentences):
            sentence_id = f"{para_id}_sent_{i+1:03d}"
            all_sentences.append((
                sentence_id,
                para_id,
                paper_id,
                sent,
                i + 1
            ))
    
    print(f"✂️  切成了 {len(all_sentences)} 个句子")
    
    # 批量插入
    batch_size = 1000
    for i in range(0, len(all_sentences), batch_size):
        batch = all_sentences[i:i+batch_size]
        conn.executemany("""
            INSERT OR REPLACE INTO sentences 
            (sentence_id, para_id, paper_id, text, sequence)
            VALUES (?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        print(f"  已插入 {min(i+batch_size, len(all_sentences))}/{len(all_sentences)}")
    
    conn.close()
    print(f"\n✅ research.db 的 sentences 表建好了！")


def build_sentences_for_abstracts_db():
    """为 abstracts.db 建 sentences 表"""
    print("\n" + "=" * 60)
    print("📝 为 abstracts.db 建 sentences 表")
    print("=" * 60)
    
    conn = sqlite3.connect(str(ABSTRACTS_DB))
    
    # 建 sentences 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentences (
            sentence_id TEXT PRIMARY KEY,
            pmid TEXT NOT NULL,
            title TEXT,
            text TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            FOREIGN KEY (pmid) REFERENCES papers(pmid)
        )
    """)
    
    # 建正向索引：pmid → 句子
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentences_pmid 
        ON sentences(pmid, sequence)
    """)
    
    # 读所有摘要
    rows = conn.execute("""
        SELECT pmid, title, abstract
        FROM papers
        WHERE abstract IS NOT NULL AND length(abstract) > 10
    """).fetchall()
    
    print(f"\n📥 读了 {len(rows)} 篇摘要")
    
    # 切分句子
    all_sentences = []
    for pmid, title, abstract in rows:
        sentences = split_into_sentences(abstract)
        
        for i, sent in enumerate(sentences):
            sentence_id = f"{pmid}_sent_{i+1:03d}"
            all_sentences.append((
                sentence_id,
                pmid,
                title,
                sent,
                i + 1
            ))
    
    print(f"✂️  切成了 {len(all_sentences)} 个句子")
    
    # 批量插入
    batch_size = 1000
    for i in range(0, len(all_sentences), batch_size):
        batch = all_sentences[i:i+batch_size]
        conn.executemany("""
            INSERT OR REPLACE INTO sentences 
            (sentence_id, pmid, title, text, sequence)
            VALUES (?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        print(f"  已插入 {min(i+batch_size, len(all_sentences))}/{len(all_sentences)}")
    
    conn.close()
    print(f"\n✅ abstracts.db 的 sentences 表建好了！")


def main():
    print("=" * 60)
    print("📊 句子切分脚本 V1.0")
    print("=" * 60)
    
    # 为 research.db 建 sentences 表
    build_sentences_for_research_db()
    
    # 为 abstracts.db 建 sentences 表
    build_sentences_for_abstracts_db()
    
    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
