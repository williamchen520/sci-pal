"""
V31.32: 句子级关联关系脚本

按照段落级关系的原则，建句子级的关系：
- 句子 ↔ 图表
- 句子 ↔ 表格
- 句子 ↔ 引用

原则：在句子的文本里，用正则表达式匹配 "Fig. 1" 或 "[1]" 等，找到对应的编号，建关联关系。
"""

import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# 路径配置
RESEARCH_DB = PROJECT_ROOT / "data" / "research.db"


def build_sentence_links():
    """建句子级的关联关系"""
    print("\n" + "=" * 60)
    print("📝 建句子级的关联关系")
    print("=" * 60)
    
    conn = sqlite3.connect(str(RESEARCH_DB))
    
    # 建句子级关联关系表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentence_links (
            link_id TEXT PRIMARY KEY,
            sentence_id TEXT NOT NULL,
            para_id TEXT NOT NULL,
            paper_id TEXT NOT NULL,
            source_type TEXT NOT NULL,  -- sentence
            target_type TEXT NOT NULL,  -- figure / table / citation
            target_id TEXT NOT NULL,
            relation TEXT NOT NULL,  -- mentions / cites
            FOREIGN KEY (sentence_id) REFERENCES sentences(sentence_id),
            FOREIGN KEY (para_id) REFERENCES paragraphs(para_id),
            FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
        )
    """)
    
    # 建索引
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentence_links_sentence 
        ON sentence_links(sentence_id)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentence_links_target 
        ON sentence_links(target_type, target_id)
    """)
    
    # 读所有句子
    rows = conn.execute("""
        SELECT sentence_id, para_id, paper_id, text
        FROM sentences
    """).fetchall()
    
    print(f"\n📥 读了 {len(rows)} 个句子")
    
    # 为每篇论文，建图表/表格/引用的编号映射
    # 先读所有论文的图表/表格/引用
    papers = {}
    
    # 读图表
    fig_rows = conn.execute("""
        SELECT paper_id, fig_id, fig_number
        FROM figures
    """).fetchall()
    
    for paper_id, fig_id, fig_number in fig_rows:
        if paper_id not in papers:
            papers[paper_id] = {"figures": {}, "tables": {}, "citations": {}}
        
        # 编号映射：Fig 1 -> fig_id
        if fig_number:
            papers[paper_id]["figures"][fig_number] = fig_id
    
    # 读表格
    table_rows = conn.execute("""
        SELECT paper_id, table_id, table_number
        FROM tables
    """).fetchall()
    
    for paper_id, table_id, table_number in table_rows:
        if paper_id not in papers:
            papers[paper_id] = {"figures": {}, "tables": {}, "citations": {}}
        
        # 编号映射：Table 1 -> table_id
        if table_number:
            papers[paper_id]["tables"][table_number] = table_id
    
    # 读引用
    cite_rows = conn.execute("""
        SELECT paper_id, citation_id, ref_number
        FROM citations
    """).fetchall()
    
    for paper_id, citation_id, ref_number in cite_rows:
        if paper_id not in papers:
            papers[paper_id] = {"figures": {}, "tables": {}, "citations": {}}
        
        # 编号映射：[1] -> citation_id
        if ref_number:
            papers[paper_id]["citations"][str(ref_number)] = citation_id
    
    print(f"📚 读了 {len(papers)} 篇论文的图表/表格/引用")
    
    # 切分句子，建关联关系
    all_links = []
    
    for sentence_id, para_id, paper_id, text in rows:
        if paper_id not in papers:
            continue
        
        paper = papers[paper_id]
        
        # 1. 找图表引用："Fig. 1" 或 "Figure 2" 等
        fig_refs = re.findall(r'(?:Fig\.?|Figure)\s*(\d+)', text, re.IGNORECASE)
        for fig_num in fig_refs:
            fig_key = f"Fig {fig_num}"
            if fig_key in paper["figures"]:
                link_id = f"link_{sentence_id}_fig_{fig_num}"
                all_links.append((
                    link_id,
                    sentence_id,
                    para_id,
                    paper_id,
                    "sentence",
                    "figure",
                    paper["figures"][fig_key],
                    "mentions"
                ))
        
        # 2. 找表格引用："Table 1" 或 "Tab. 2" 等
        table_refs = re.findall(r'(?:Table|Tab\.?)\s*(\d+)', text, re.IGNORECASE)
        for table_num in table_refs:
            table_key = f"Table {table_num}"
            if table_key in paper["tables"]:
                link_id = f"link_{sentence_id}_tab_{table_num}"
                all_links.append((
                    link_id,
                    sentence_id,
                    para_id,
                    paper_id,
                    "sentence",
                    "table",
                    paper["tables"][table_key],
                    "mentions"
                ))
        
        # 3. 找引用引用：[1] 或 [2] 等
        cite_refs = re.findall(r'\[(\d+)\]', text)
        for cite_num in cite_refs:
            if cite_num in paper["citations"]:
                link_id = f"link_{sentence_id}_cite_{cite_num}"
                all_links.append((
                    link_id,
                    sentence_id,
                    para_id,
                    paper_id,
                    "sentence",
                    "citation",
                    paper["citations"][cite_num],
                    "cites"
                ))
    
    print(f"🔗 建了 {len(all_links)} 个关联关系")
    
    # 批量插入
    batch_size = 1000
    for i in range(0, len(all_links), batch_size):
        batch = all_links[i:i+batch_size]
        conn.executemany("""
            INSERT OR REPLACE INTO sentence_links 
            (link_id, sentence_id, para_id, paper_id, source_type, target_type, target_id, relation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        print(f"  已插入 {min(i+batch_size, len(all_links))}/{len(all_links)}")
    
    conn.close()
    print(f"\n✅ 句子级关联关系建好了！")


def main():
    print("=" * 60)
    print("📊 句子级关联关系脚本 V1.0")
    print("=" * 60)
    
    build_sentence_links()
    
    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
