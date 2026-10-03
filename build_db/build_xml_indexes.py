#!/usr/bin/env python3
"""
为 xml.db 建内部索引关系 V1.0

包括：
  - 段落到句子的正向索引
  - 句子到图表的正反向索引
  - 句子到引用的正反向索引

使用方法：
  python build_db\build_xml_indexes.py
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def build_indexes(db_path: str):
    """为 xml.db 建内部索引关系"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 60)
    print("📊 为 xml.db 建内部索引关系")
    print("=" * 60)

    # ============================================================
    # 1. 段落到句子的正向索引
    # ============================================================
    print("\n🔧 建段落到句子的正向索引...")

    # 摘要段落 → 句子
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_abstract_paragraphs_paper_id
        ON abstract_paragraphs(paper_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentences_abstract_paragraph
        ON sentences(paragraph_id)
        WHERE paragraph_type = 'abstract'
    """)

    # 正文段落 → 句子
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_body_paragraphs_paper_id
        ON body_paragraphs(paper_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentences_body_paragraph
        ON sentences(paragraph_id)
        WHERE paragraph_type = 'body'
    """)

    print("  ✅ 段落到句子的正向索引建好了！")

    # ============================================================
    # 2. 论文 → 段落/句子/引用 的索引
    # ============================================================
    print("\n🔧 建论文 → 段落/句子/引用 的索引...")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pmc_pmcid
        ON papers(pmcid)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sentences_paper_id
        ON sentences(paper_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ref_list_paper_id
        ON ref_list(paper_id)
    """)

    print("  ✅ 论文 → 段落/句子/引用 的索引建好了！")

    # ============================================================
    # 3. 按章节的索引
    # ============================================================
    print("\n🔧 建按章节的索引...")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_body_paragraphs_section_title
        ON body_paragraphs(section_title)
    """)

    print("  ✅ 按章节的索引建好了！")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="为 xml.db 建内部索引关系")
    parser.add_argument("--db-path", type=str, default="data/xml.db", help="数据库路径")

    args = parser.parse_args()

    build_indexes(args.db_path)


if __name__ == "__main__":
    main()
