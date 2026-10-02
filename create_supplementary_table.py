#!/usr/bin/env python3
"""V25.17 手动创建 supplementary_files 表
运行方式: python3 create_supplementary_table.py
"""
import sqlite3
import sys
from pathlib import Path

# 数据库路径（和 api_server.py 里的一致）
PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

if not DB_PATH.exists():
    print(f"❌ 数据库文件不存在: {DB_PATH}")
    print("请确认你在项目根目录运行此脚本")
    sys.exit(1)

print(f"📂 数据库: {DB_PATH}")

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 检查表是否已存在
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='supplementary_files'")
exists = cursor.fetchone()

if exists:
    print("✅ supplementary_files 表已存在，无需创建")
else:
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supplementary_files (
        supp_id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_type TEXT,
        file_path TEXT,
        file_size INTEGER,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
    )
    ''')
    conn.commit()
    print("✅ supplementary_files 表创建成功")

# 验证
cursor.execute("PRAGMA table_info(supplementary_files)")
columns = cursor.fetchall()
print(f"\n📋 表结构 ({len(columns)} 列):")
for col in columns:
    print(f"   - {col[1]} ({col[2]})")

conn.close()
print("\n✅ 完成！现在可以正常使用补充材料功能了")
