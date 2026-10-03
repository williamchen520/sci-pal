#!/usr/bin/env python3
"""
为 xml.db 建 FTS5 全文索引 V1.0

使用方法：
  python build_db\build_xml_fts.py
"""

import argparse
import sqlite3
from pathlib import Path


def build_fts(db_path: str):
    """为 xml.db 建 FTS5 全文索引"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 60)
    print("📊 为 xml.db 建 FTS5 全文索引")
    print("=" * 60)

    # ============================================================
    # 1. 建摘要段落的 FTS5 索引
    # ============================================================
    print("\n🔧 建摘要段落的 FTS5 索引...")

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS abstract_paragraphs_fts
        USING fts5(
            paper_id,
            text,
            content='abstract_paragraphs',
            content_rowid='id'
        )
    """)

    # 同步数据
    cursor.execute("""
        INSERT INTO abstract_paragraphs_fts (rowid, paper_id, text)
        SELECT id, paper_id, text FROM abstract_paragraphs
    """)

    print("  ✅ 摘要段落的 FTS5 索引建好了！")

    # ============================================================
    # 2. 建正文段落的 FTS5 索引
    # ============================================================
    print("\n🔧 建正文段落的 FTS5 索引...")

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS body_paragraphs_fts
        USING fts5(
            paper_id,
            section_title,
            text,
            content='body_paragraphs',
            content_rowid='id'
        )
    """)

    # 同步数据
    cursor.execute("""
        INSERT INTO body_paragraphs_fts (rowid, paper_id, section_title, text)
        SELECT id, paper_id, section_title, text FROM body_paragraphs
    """)

    print("  ✅ 正文段落的 FTS5 索引建好了！")

    # ============================================================
    # 3. 建句子的 FTS5 索引
    # ============================================================
    print("\n🔧 建句子的 FTS5 索引...")

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS sentences_fts
        USING fts5(
            paper_id,
            paragraph_type,
            paragraph_id,
            text,
            content='sentences',
            content_rowid='id'
        )
    """)

    # 同步数据
    cursor.execute("""
        INSERT INTO sentences_fts (rowid, paper_id, paragraph_type, paragraph_id, text)
        SELECT id, paper_id, paragraph_type, paragraph_id, text FROM sentences
    """)

    print("  ✅ 句子的 FTS5 索引建好了！")

    # ============================================================
    # 4. 建论文的 FTS5 索引（标题、关键词、摘要）
    # ============================================================
    print("\n🔧 建论文的 FTS5 索引...")

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts
        USING fts5(
            pmcid,
            title,
            journal,
            publish_date
        )
    """)

    # 同步数据
    cursor.execute("""
        INSERT INTO papers_fts (pmcid, title, journal, publish_date)
        SELECT pmcid, title, journal, publish_date FROM papers
    """)

    print("  ✅ 论文的 FTS5 索引建好了！")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="为 xml.db 建 FTS5 全文索引")
    parser.add_argument("--db-path", type=str, default="data/xml.db", help="数据库路径")

    args = parser.parse_args()

    build_fts(args.db_path)


if __name__ == "__main__":
    main()
