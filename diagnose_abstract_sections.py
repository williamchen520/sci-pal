#!/usr/bin/env python3
"""
诊断脚本：查看每篇论文中 section_level1 包含 abstract 的段落情况
用法: python3 diagnose_abstract_sections.py data/research.db
"""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "data/research.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 获取所有论文
cursor.execute("SELECT paper_id, title FROM papers ORDER BY paper_id")
papers = cursor.fetchall()

print(f"总论文数: {len(papers)}")
print("=" * 80)

# 统计所有出现过的 section_level1 值
print("\n【所有出现过的 section_level1 值统计】")
cursor.execute("""
    SELECT section_level1, COUNT(*) as cnt
    FROM paragraphs
    WHERE section_level1 IS NOT NULL AND section_level1 != ''
    GROUP BY section_level1
    ORDER BY cnt DESC
    LIMIT 30
""")
for row in cursor.fetchall():
    print(f"  {row[1]:4d}  {row[0]}")

print("\n" + "=" * 80)
print("\n【每篇论文的 abstract 相关段落】")

found_count = 0
for paper_id, title in papers:
    cursor.execute("""
        SELECT para_id, section_level1, section_level2, substr(text, 1, 120) as preview, sequence
        FROM paragraphs
        WHERE paper_id = ?
          AND (
              lower(section_level1) LIKE '%abstract%'
              OR lower(section_level2) LIKE '%abstract%'
              OR lower(section_level1) LIKE '%summary%'
              OR lower(section_level1) LIKE '%highlights%'
          )
        ORDER BY sequence
    """, (paper_id,))
    rows = cursor.fetchall()
    if rows:
        found_count += 1
        print(f"\n📄 [{found_count}] {title[:60]}")
        for r in rows:
            print(f"   seq={r[4]:3d}  L1='{r[1]}'  L2='{r[2]}'")
            print(f"   预览: {r[3]}...")

print(f"\n{'=' * 80}")
print(f"包含 abstract/summary/highlights 标题的论文数: {found_count}/{len(papers)}")

# 再看看前3篇论文的前10个段落，了解没有abstract标题的论文结构
print(f"\n{'=' * 80}")
print("【前5篇论文的前8个段落结构（看摘要实际长什么样）】")
for paper_id, title in papers[:5]:
    cursor.execute("""
        SELECT sequence, section_level1, section_level2, substr(text, 1, 80) as preview
        FROM paragraphs
        WHERE paper_id = ?
        ORDER BY sequence
        LIMIT 8
    """, (paper_id,))
    rows = cursor.fetchall()
    print(f"\n📄 {title[:60]}")
    for r in rows:
        print(f"   seq={r[0]:2d}  L1='{r[1] or '':20s}'  L2='{r[2] or '':15s}'  {r[3]}...")

conn.close()
