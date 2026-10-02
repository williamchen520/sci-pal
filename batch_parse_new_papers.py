#!/usr/bin/env python3
"""
V25.18 智能批量解析脚本：只解析 documents 目录下还未入库的 PDF
自动跳过已解析的论文，只处理新增的。

用法:
    python3 batch_parse_new_papers.py [documents目录] [数据库路径]

示例:
    python3 batch_parse_new_papers.py documents data/research.db
"""

import os
import sys
import hashlib
import time
import sqlite3
from pathlib import Path

# 添加项目根目录到 path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 模型配置 - 使用国内镜像，禁用 Xet
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["HF_HUB_OFFLINE"] = "0"


def generate_paper_id(pdf_path: str) -> str:
    """复现 ParserOrchestrator 的 paper_id 生成逻辑"""
    with open(pdf_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()[:12]
    filename = os.path.basename(pdf_path).replace(".pdf", "")
    clean_name = "".join(c if c.isalnum() else "_" for c in filename)[:50]
    return f"paper_{clean_name}_{file_hash}"


def get_parsed_paper_ids(db_path: str) -> set:
    """从数据库获取所有已解析的 paper_id"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT paper_id FROM papers")
    paper_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    return paper_ids


def batch_parse_new(documents_dir: str = "documents", db_path: str = "data/research.db"):
    print("=" * 70)
    print("🔬 V25.18 智能批量解析（只解析新增论文）")
    print("=" * 70)
    print(f"📂 PDF 目录: {documents_dir}")
    print(f"🗄️  数据库: {db_path}")

    # 检查目录和数据库
    if not os.path.isdir(documents_dir):
        print(f"❌ PDF 目录不存在: {documents_dir}")
        return

    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return

    # ── 1. 扫描所有 PDF ──
    print("\n── 1. 扫描 PDF 文件 ──")
    pdf_files = sorted([
        os.path.join(documents_dir, f)
        for f in os.listdir(documents_dir)
        if f.lower().endswith('.pdf')
    ])
    print(f"   找到 {len(pdf_files)} 个 PDF 文件")

    # ── 2. 获取已解析的 paper_id ──
    print("\n── 2. 检查已解析论文 ──")
    parsed_ids = get_parsed_paper_ids(db_path)
    print(f"   数据库中已有 {len(parsed_ids)} 篇论文")

    # ── 3. 筛选未解析的 PDF ──
    print("\n── 3. 筛选待解析论文 ──")
    to_parse = []
    skipped = []

    for pdf_path in pdf_files:
        try:
            paper_id = generate_paper_id(pdf_path)
            if paper_id in parsed_ids:
                skipped.append((pdf_path, paper_id))
            else:
                to_parse.append((pdf_path, paper_id))
        except Exception as e:
            print(f"   ⚠️  无法处理 {os.path.basename(pdf_path)}: {e}")

    print(f"   ✅ 已解析（跳过）: {len(skipped)} 篇")
    print(f"   🔄 待解析（新增）: {len(to_parse)} 篇")

    if not to_parse:
        print("\n🎉 所有 PDF 都已解析，没有新增论文需要处理！")
        return

    # 显示待解析列表
    print("\n   待解析论文列表:")
    for i, (pdf_path, paper_id) in enumerate(to_parse, 1):
        print(f"   [{i}] {os.path.basename(pdf_path)}")
        print(f"        paper_id: {paper_id}")

    # ── 4. 初始化解析器 ──
    print("\n── 4. 初始化解析引擎 ──")
    print("   正在加载 Docling 模型...")

    from build_db.parsers.parser_orchestrator import ParserOrchestrator
    from build_db.db_writer import DatabaseWriter

    orchestrator = ParserOrchestrator()
    db_writer = DatabaseWriter(db_path=db_path)
    print("   ✅ 解析引擎就绪！")

    # ── 5. 逐个解析 ──
    print(f"\n── 5. 开始解析（共 {len(to_parse)} 篇）──")
    print("=" * 70)

    results = []
    total_start = time.time()

    for i, (pdf_path, paper_id) in enumerate(to_parse, 1):
        filename = os.path.basename(pdf_path)
        print(f"\n[{i}/{len(to_parse)}] 📄 解析: {filename}")
        print(f"   Paper ID: {paper_id}")
        start = time.time()

        try:
            # 解析
            parsed_result = orchestrator.parse_paper(pdf_path, paper_id=paper_id)

            # 入库
            success = db_writer.insert_paper(parsed_result)

            elapsed = time.time() - start
            para_count = len(parsed_result.get('paragraphs', []))
            fig_count = len(parsed_result.get('figures', []))
            table_count = len(parsed_result.get('tables', []))

            if success:
                print(f"   ✅ 解析成功！{para_count} 段落 / {fig_count} 图 / {table_count} 表 / {elapsed:.1f}s")
                results.append({
                    'filename': filename,
                    'paper_id': paper_id,
                    'status': 'success',
                    'paragraphs': para_count,
                    'figures': fig_count,
                    'tables': table_count,
                    'time_sec': round(elapsed, 1),
                })
            else:
                print(f"   ❌ 入库失败")
                results.append({
                    'filename': filename,
                    'paper_id': paper_id,
                    'status': 'db_insert_failed',
                    'paragraphs': para_count,
                    'figures': fig_count,
                    'tables': table_count,
                    'time_sec': round(elapsed, 1),
                })

        except Exception as e:
            elapsed = time.time() - start
            print(f"   ❌ 解析出错: {str(e)[:200]}")
            results.append({
                'filename': filename,
                'paper_id': paper_id,
                'status': f'error: {str(e)[:200]}',
                'paragraphs': 0,
                'figures': 0,
                'tables': 0,
                'time_sec': round(elapsed, 1),
            })

    # ── 6. 汇总统计 ──
    total_time = time.time() - total_start
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = len(results) - success_count
    total_paragraphs = sum(r['paragraphs'] for r in results)
    total_figures = sum(r['figures'] for r in results)
    total_tables = sum(r['tables'] for r in results)

    print("\n" + "=" * 70)
    print("📊 批量解析完成！")
    print("=" * 70)
    print(f"  待解析总数:     {len(to_parse)} 篇")
    print(f"  ✅ 解析成功:     {success_count} 篇")
    print(f"  ❌ 解析失败:     {failed_count} 篇")
    print(f"  ─────────────────────────────")
    print(f"  新增段落:       {total_paragraphs} 段")
    print(f"  新增图表:       {total_figures} 图")
    print(f"  新增表格:       {total_tables} 表")
    print(f"  ─────────────────────────────")
    print(f"  总耗时:         {total_time:.1f}s ({total_time/60:.1f} min)")
    if success_count > 0:
        print(f"  平均每篇:       {total_time/success_count:.1f}s")

    # 失败列表
    if failed_count > 0:
        print(f"\n❌ 失败的论文:")
        for r in results:
            if r['status'] != 'success':
                print(f"   - {r['filename']}")
                print(f"     原因: {r['status'][:100]}")

    # 后续提示
    print("\n" + "=" * 70)
    print("💡 后续步骤")
    print("=" * 70)
    print("  1. 构建向量索引:  python -m build_db.build_embeddings")
    print("  2. 构建 FTS 索引: python -m build_db.build_fts")
    print("  3. 构建知识图谱:   python -m build_db.build_paper_graph")
    print("  4. 运行自检:       python3 scripts/self_check.py")
    print("=" * 70)


if __name__ == '__main__':
    documents_dir = sys.argv[1] if len(sys.argv) > 1 else 'documents'
    db_path = sys.argv[2] if len(sys.argv) > 2 else 'data/research.db'
    batch_parse_new(documents_dir, db_path)
