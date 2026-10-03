#!/usr/bin/env python3
"""
建联合索引 V1.0

把多个数据库（research.db、abstracts.db、xml.db）联合起来，
建一个联合索引，注意去重。

使用方法：
  python build_db\build_unified_index.py
"""

import argparse
import sqlite3
from pathlib import Path


def build_unified_index(db_paths: list[str], output_db: str):
    """建联合索引"""
    print("=" * 60)
    print("📊 建联合索引")
    print("=" * 60)

    # 创建输出数据库
    conn = sqlite3.connect(output_db)
    cursor = conn.cursor()

    # ============================================================
    # 1. 建联合论文表
    # ============================================================
    print("\n🔧 建联合论文表...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unified_papers (
            paper_id TEXT PRIMARY KEY,  -- 用 paper_id 作为主键
            pmcid TEXT,
            pmid TEXT,
            doi TEXT,
            title TEXT,
            authors TEXT,
            abstract TEXT,
            journal TEXT,
            publish_date TEXT,
            source_db TEXT  -- 来源数据库：'research.db'、'abstracts.db'、'xml.db'
        )
    """)

    print("  ✅ 联合论文表建好了！")

    # ============================================================
    # 2. 从各个数据库导入论文
    # ============================================================
    for db_path in db_paths:
        print(f"\n🔧 从 {db_path} 导入论文...")

        # 连接到源数据库
        source_conn = sqlite3.connect(db_path)
        source_cursor = source_conn.cursor()

        # 从 research.db 导入
        if "research.db" in db_path:
            # research.db 的 papers 表有 paper_id、title、authors、abstract、journal、year、doi 等字段
            source_cursor.execute("""
                SELECT paper_id, title, authors, abstract, journal, year, doi FROM papers
            """)
            rows = source_cursor.fetchall()

            for row in rows:
                paper_id, title, authors, abstract, journal, year, doi = row

                # 插入到联合论文表（注意去重）
                cursor.execute("""
                    INSERT OR IGNORE INTO unified_papers (
                        paper_id, title, authors, abstract, journal, publish_date, doi, source_db
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (paper_id, title, authors, abstract, journal, str(year) if year else None, doi, "research.db"))

            print(f"  ✅ 从 research.db 导入了 {len(rows)} 篇论文！")

        # 从 abstracts.db 导入
        elif "abstracts.db" in db_path:
            # 假设 abstracts.db 有 papers 表
            source_cursor.execute("""
                SELECT pmcid, pmid, doi, title, abstract FROM papers
            """)
            rows = source_cursor.fetchall()

            for row in rows:
                pmcid, pmid, doi, title, abstract = row
                paper_id = pmcid if pmcid else pmid

                # 插入到联合论文表（注意去重）
                cursor.execute("""
                    INSERT OR IGNORE INTO unified_papers (
                        paper_id, pmcid, pmid, doi, title, abstract, source_db
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (paper_id, pmcid, pmid, doi, title, abstract, "abstracts.db"))

            print(f"  ✅ 从 abstracts.db 导入了 {len(rows)} 篇论文！")

        # 从 xml.db 导入
        elif "xml.db" in db_path:
            # 假设 xml.db 有 papers 表
            source_cursor.execute("""
                SELECT pmcid, pmid, doi, title, journal, publish_date FROM papers
            """)
            rows = source_cursor.fetchall()

            for row in rows:
                pmcid, pmid, doi, title, journal, publish_date = row
                paper_id = pmcid if pmcid else pmid

                # 插入到联合论文表（注意去重）
                cursor.execute("""
                    INSERT OR IGNORE INTO unified_papers (
                        paper_id, pmcid, pmid, doi, title, journal, publish_date, source_db
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (paper_id, pmcid, pmid, doi, title, journal, publish_date, "xml.db"))

            print(f"  ✅ 从 xml.db 导入了 {len(rows)} 篇论文！")

        source_conn.close()

    conn.commit()

    # ============================================================
    # 3. 建联合 FTS5 索引
    # ============================================================
    print("\n🔧 建联合 FTS5 索引...")

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS unified_papers_fts
        USING fts5(
            paper_id,
            title,
            journal,
            abstract,
            content='unified_papers',
            content_rowid='rowid'
        )
    """)

    # 同步数据
    cursor.execute("""
        INSERT INTO unified_papers_fts (rowid, paper_id, title, journal, abstract)
        SELECT rowid, paper_id, title, journal, abstract FROM unified_papers
    """)

    print("  ✅ 联合 FTS5 索引建好了！")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)
    print(f"  输出数据库: {output_db}")


def main():
    parser = argparse.ArgumentParser(description="建联合索引")
    parser.add_argument("--db-paths", nargs="+", default=[
        "data/research.db",
        "data/abstracts.db",
        "data/xml.db"
    ], help="源数据库路径列表")
    parser.add_argument("--output-db", type=str, default="data/unified.db", help="输出数据库路径")

    args = parser.parse_args()

    build_unified_index(args.db_paths, args.output_db)


if __name__ == "__main__":
    main()
