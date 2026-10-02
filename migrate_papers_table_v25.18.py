#!/usr/bin/env python3
"""
V25.18 数据库迁移脚本：给 papers 表补充新字段

新增字段：
- abstract TEXT
- paper_type TEXT DEFAULT 'J'
- publisher TEXT
- language TEXT DEFAULT 'en'
- affiliations TEXT
- funding TEXT
- parse_status TEXT DEFAULT 'completed'
- parse_engine TEXT
- updated_at TEXT DEFAULT CURRENT_TIMESTAMP

用法：
  python3 migrate_papers_table_v25.18.py [数据库路径]

默认数据库路径：data/research.db
"""

import os
import sqlite3
import sys


def get_current_columns(cursor, table_name: str) -> set[str]:
    """获取表当前的列名集合。"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def migrate_papers_table(db_path: str) -> None:
    """迁移 papers 表，添加缺失的字段。"""
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    print(f"📂 数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 定义需要添加的新字段（列名, 列定义）
    # 注意：SQLite 的 ALTER TABLE ADD COLUMN 不允许 CURRENT_TIMESTAMP 作为默认值
    # 所以 updated_at 先不带默认值添加，后面用 UPDATE 填充
    new_columns = [
        ("abstract", "TEXT"),
        ("paper_type", "TEXT DEFAULT 'J'"),
        ("publisher", "TEXT"),
        ("language", "TEXT DEFAULT 'en'"),
        ("affiliations", "TEXT"),
        ("funding", "TEXT"),
        ("parse_status", "TEXT DEFAULT 'completed'"),
        ("parse_engine", "TEXT"),
        ("updated_at", "TEXT"),
    ]

    # 获取当前列
    current_cols = get_current_columns(cursor, "papers")
    print(f"📋 当前 papers 表有 {len(current_cols)} 列")

    # 添加缺失的列
    added = 0
    for col_name, col_def in new_columns:
        if col_name not in current_cols:
            print(f"  ➕ 添加列: {col_name} ({col_def})")
            cursor.execute(f"ALTER TABLE papers ADD COLUMN {col_name} {col_def}")
            added += 1
        else:
            print(f"  ✓ 已存在: {col_name}")

    # 给已有记录设置默认值（对于没有默认值的列）
    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]
    print(f"\n📊 论文总数: {total}")

    # 更新 parse_status 和 language 的默认值（如果为 NULL）
    cursor.execute("UPDATE papers SET parse_status = 'completed' WHERE parse_status IS NULL OR parse_status = ''")
    cursor.execute("UPDATE papers SET language = 'en' WHERE language IS NULL OR language = ''")
    cursor.execute("UPDATE papers SET paper_type = 'J' WHERE paper_type IS NULL OR paper_type = ''")
    cursor.execute("UPDATE papers SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")

    conn.commit()

    # 验证
    final_cols = get_current_columns(cursor, "papers")
    print(f"\n✅ 迁移完成！")
    print(f"   新增列数: {added}")
    print(f"   最终列数: {len(final_cols)}")
    print(f"   最终列: {sorted(final_cols)}")

    conn.close()


if __name__ == "__main__":
    # 默认数据库路径
    default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "research.db")
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db

    print("=" * 60)
    print("V25.18 数据库迁移：papers 表补充新字段")
    print("=" * 60)
    print()

    migrate_papers_table(db_path)

    print()
    print("=" * 60)
