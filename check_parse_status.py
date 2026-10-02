#!/usr/bin/env python3
"""
V25.18 诊断脚本：检查每篇论文的解析状态
检查内容：
1. papers 表中的所有论文
2. 每篇论文的段落数、图表数、表格数、引用数
3. parse_status 字段
4. 识别解析失败或解析不完整的论文
"""

import sqlite3
import sys
import os


def check_parse_status(db_path):
    print("=" * 70)
    print("🔍 Sci-Pal 论文解析状态诊断")
    print("=" * 70)
    print(f"📂 数据库: {db_path}")

    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ── 1. 检查 papers 表结构 ──
    print("\n── 1. papers 表结构 ──")
    cursor.execute("PRAGMA table_info(papers)")
    columns = [row['name'] for row in cursor.fetchall()]
    print(f"   共 {len(columns)} 列: {', '.join(columns)}")

    has_parse_status = 'parse_status' in columns
    print(f"   parse_status 字段: {'✅ 存在' if has_parse_status else '❌ 不存在'}")

    # ── 2. 统计总数 ──
    print("\n── 2. 总体统计 ──")
    cursor.execute("SELECT COUNT(*) as cnt FROM papers")
    total_papers = cursor.fetchone()['cnt']
    print(f"   论文总数: {total_papers}")

    cursor.execute("SELECT COUNT(*) as cnt FROM paragraphs")
    total_paras = cursor.fetchone()['cnt']
    print(f"   段落总数: {total_paras}")

    cursor.execute("SELECT COUNT(*) as cnt FROM figures")
    total_figs = cursor.fetchone()['cnt']
    print(f"   图表总数: {total_figs}")

    cursor.execute("SELECT COUNT(*) as cnt FROM tables")
    total_tables = cursor.fetchone()['cnt']
    print(f"   表格总数: {total_tables}")

    cursor.execute("SELECT COUNT(*) as cnt FROM citations")
    total_cites = cursor.fetchone()['cnt']
    print(f"   引用总数: {total_cites}")

    # ── 3. 每篇论文的详细解析状态 ──
    print("\n── 3. 每篇论文解析状态 ──")
    print(f"{'序号':>4} {'paper_id':<45} {'段落':>6} {'图表':>5} {'表格':>5} {'引用':>5} {'状态':<12} {'标题'}")
    print("-" * 140)

    # 构建查询
    status_col = 'parse_status' if has_parse_status else "NULL as parse_status"

    query = f"""
    SELECT
        p.paper_id,
        p.title,
        {status_col},
        (SELECT COUNT(*) FROM paragraphs para WHERE para.paper_id = p.paper_id) as para_count,
        (SELECT COUNT(*) FROM figures f WHERE f.paper_id = p.paper_id) as fig_count,
        (SELECT COUNT(*) FROM tables t WHERE t.paper_id = p.paper_id) as table_count,
        (SELECT COUNT(*) FROM citations c WHERE c.paper_id = p.paper_id) as cite_count
    FROM papers p
    ORDER BY p.paper_id
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    failed_papers = []
    incomplete_papers = []
    success_papers = []

    for idx, row in enumerate(rows, 1):
        paper_id = row['paper_id']
        title = (row['title'] or '(无标题)')[:50]
        status = row['parse_status'] or 'N/A'
        para_count = row['para_count']
        fig_count = row['fig_count']
        table_count = row['table_count']
        cite_count = row['cite_count']

        # 判断解析状态
        if para_count == 0:
            status_flag = "❌ 失败"
            failed_papers.append((idx, paper_id, title, para_count, fig_count))
        elif para_count < 10:
            status_flag = "⚠️  不完整"
            incomplete_papers.append((idx, paper_id, title, para_count, fig_count))
        else:
            status_flag = "✅ 成功"
            success_papers.append((idx, paper_id, title, para_count, fig_count))

        print(f"{idx:>4} {paper_id:<45} {para_count:>6} {fig_count:>5} {table_count:>5} {cite_count:>5} {status:<12} {title}")

    # ── 4. 汇总 ──
    print("\n" + "=" * 70)
    print("📊 解析状态汇总")
    print("=" * 70)
    print(f"  总论文数:     {total_papers}")
    print(f"  ✅ 解析成功:   {len(success_papers)} 篇 (段落数 >= 10)")
    print(f"  ⚠️  解析不完整: {len(incomplete_papers)} 篇 (段落数 < 10)")
    print(f"  ❌ 解析失败:   {len(failed_papers)} 篇 (段落数 = 0)")

    if failed_papers:
        print("\n❌ 解析失败的论文（段落数为0）:")
        for idx, paper_id, title, para_count, fig_count in failed_papers:
            print(f"   [{idx}] {paper_id}")
            print(f"       标题: {title}")
            print(f"       段落: {para_count}, 图表: {fig_count}")

    if incomplete_papers:
        print("\n⚠️  解析不完整的论文（段落数 < 10）:")
        for idx, paper_id, title, para_count, fig_count in incomplete_papers:
            print(f"   [{idx}] {paper_id}")
            print(f"       标题: {title}")
            print(f"       段落: {para_count}, 图表: {fig_count}")

    # ── 5. 检查 parse_status 字段分布 ──
    if has_parse_status:
        print("\n── 4. parse_status 字段分布 ──")
        cursor.execute("SELECT parse_status, COUNT(*) as cnt FROM papers GROUP BY parse_status")
        for row in cursor.fetchall():
            print(f"   {row['parse_status'] or '(NULL)'}: {row['cnt']} 篇")

    # ── 6. 检查有没有 papers 表有记录但 paragraphs 完全没有的 ──
    print("\n── 5. 数据一致性检查 ──")
    cursor.execute("""
        SELECT p.paper_id, p.title
        FROM papers p
        WHERE NOT EXISTS (
            SELECT 1 FROM paragraphs para WHERE para.paper_id = p.paper_id
        )
    """)
    no_para_papers = cursor.fetchall()
    if no_para_papers:
        print(f"   ❌ 有 {len(no_para_papers)} 篇论文在 papers 表中但没有任何段落:")
        for row in no_para_papers:
            print(f"      - {row['paper_id']}: {row['title'][:50]}")
    else:
        print("   ✅ 所有论文都有至少一个段落")

    # 检查反向：paragraphs 里有 paper_id 但 papers 表里没有
    cursor.execute("""
        SELECT DISTINCT para.paper_id
        FROM paragraphs para
        WHERE NOT EXISTS (
            SELECT 1 FROM papers p WHERE p.paper_id = para.paper_id
        )
    """)
    orphan_paras = cursor.fetchall()
    if orphan_paras:
        print(f"   ❌ 有 {len(orphan_paras)} 个段落的 paper_id 在 papers 表中不存在:")
        for row in orphan_paras:
            print(f"      - {row['paper_id']}")
    else:
        print("   ✅ 所有段落的 paper_id 都有效")

    conn.close()
    print("\n" + "=" * 70)
    print("✅ 诊断完成")
    print("=" * 70)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 check_parse_status.py <数据库路径>")
        print("示例: python3 check_parse_status.py data/research.db")
        sys.exit(1)

    db_path = sys.argv[1]
    check_parse_status(db_path)
