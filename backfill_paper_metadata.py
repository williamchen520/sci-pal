#!/usr/bin/env python3
"""
V25.18 批量填充脚本：从已解析段落中反向提取 abstract/affiliations/funding

不需要重新跑 Docling，直接从数据库已有的 paragraphs 表中提取元数据。

用法:
  python3 backfill_paper_metadata.py [数据库路径]

默认数据库路径: data/research.db
"""

import os
import re
import sqlite3
import sys
from pathlib import Path

# 项目根目录
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR
sys.path.insert(0, str(PROJECT_ROOT))

from build_db.parsers.journal_optimizer import extract_metadata_fields, detect_journal_family


def get_paper_paragraphs(cursor, paper_id: str) -> list[dict]:
    """从数据库读取一篇论文的所有段落，按顺序排列。

    注意：paragraphs 表实际字段是 section_level1/2/3, text, sequence
    这里转换成 journal_optimizer 期望的格式（section_title, section_type, text_content）

    关键：section_level1 通常是论文标题，section_level2 才是真正的章节标题
    所以优先用 L2 作为 section_title，L2 为空时用 L1
    """
    cursor.execute("""
        SELECT para_id, section_level1, section_level2, section_level3, text, sequence
        FROM paragraphs
        WHERE paper_id = ?
        ORDER BY sequence ASC
    """, (paper_id,))
    rows = cursor.fetchall()
    paragraphs = []
    for row in rows:
        l1 = (row[1] or '').strip()
        l2 = (row[2] or '').strip()
        l3 = (row[3] or '').strip()

        # 优先用 L2 作为章节标题（L1 通常是论文标题），L2 为空时用 L1 或 L3
        section_title = l2 or l1 or l3 or ''

        # 同时检查 L1 和 L2 来推断 section_type
        title_for_detect = (l2 + ' ' + l1).strip().lower()
        section_type = 'body'
        if any(kw in title_for_detect for kw in ('abstract', 'summary', 'highlights', 'graphical abstract')):
            section_type = 'abstract'
        elif any(kw in title_for_detect for kw in ('methods', 'materials and methods', 'experimental procedures',
                                                      'star methods', 'online-only methods', 'supplementary methods')):
            section_type = 'methods'
        elif any(kw in title_for_detect for kw in ('references', 'bibliography', 'works cited')):
            section_type = 'references'
        elif any(kw in title_for_detect for kw in ('acknowledg', 'funding', 'financial support', 'grant information')):
            section_type = 'funding'
        elif any(kw in title_for_detect for kw in ('affiliation', 'institution')):
            section_type = 'affiliations'
        elif re.match(r'^(\d+\.?\s*)?introduction$', title_for_detect):
            section_type = 'intro'

        paragraphs.append({
            'para_id': row[0],
            'section_title': section_title,
            'section_type': section_type,
            'text_content': row[4] or '',
            'order_index': row[5],
        })
    return paragraphs


def backfill_paper_metadata(db_path: str) -> None:
    """批量填充所有论文的元数据字段。"""
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    print(f"📂 数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取所有论文
    cursor.execute("SELECT paper_id, title, journal, doi FROM papers ORDER BY paper_id")
    papers = cursor.fetchall()
    total = len(papers)
    print(f"📊 论文总数: {total}")
    print()

    # 统计
    stats = {
        'abstract': 0,
        'affiliations': 0,
        'funding': 0,
        'skipped': 0,
        'errors': 0,
    }

    for idx, (paper_id, title, journal, doi) in enumerate(papers, 1):
        try:
            # 检查是否已经有 abstract（避免重复处理）
            cursor.execute("SELECT abstract FROM papers WHERE paper_id = ?", (paper_id,))
            existing_abstract = cursor.fetchone()[0]
            if existing_abstract and len(existing_abstract) > 50:
                stats['skipped'] += 1
                if idx % 10 == 0 or idx == total:
                    print(f"  [{idx}/{total}] 跳过（已有abstract）: {title[:50]}...")
                continue

            # 读取段落
            paragraphs = get_paper_paragraphs(cursor, paper_id)
            if not paragraphs:
                stats['skipped'] += 1
                continue

            # 构建 parsed_result 格式
            metadata = {
                'title': title or '',
                'journal': journal or '',
                'doi': doi or '',
            }
            parsed_result = {
                'metadata': metadata,
                'paragraphs': paragraphs,
            }

            # 检测期刊家族（用于优化提取）
            family, _ = detect_journal_family(metadata)

            # 提取元数据字段
            extracted = extract_metadata_fields(parsed_result, family)

            # 更新数据库
            update_fields = []
            update_values = []
            for field in ['abstract', 'affiliations', 'funding']:
                if extracted.get(field):
                    update_fields.append(f"{field} = ?")
                    update_values.append(extracted[field])
                    stats[field] += 1

            if update_fields:
                update_values.append(paper_id)
                cursor.execute(
                    f"UPDATE papers SET {', '.join(update_fields)} WHERE paper_id = ?",
                    tuple(update_values)
                )

            if idx % 10 == 0 or idx == total:
                extracted_list = [k for k, v in extracted.items() if v]
                print(f"  [{idx}/{total}] {title[:50]}... -> 提取: {', '.join(extracted_list) if extracted_list else '无'}")

        except Exception as e:
            stats['errors'] += 1
            print(f"  ❌ [{idx}/{total}] 错误: {title[:50]}... -> {e}")

    conn.commit()

    # 最终统计
    print()
    print("=" * 60)
    print("📊 填充结果统计")
    print("=" * 60)
    print(f"  总论文数:     {total}")
    print(f"  提取 abstract:     {stats['abstract']} 篇")
    print(f"  提取 affiliations: {stats['affiliations']} 篇")
    print(f"  提取 funding:      {stats['funding']} 篇")
    print(f"  跳过（已有/无段落）: {stats['skipped']} 篇")
    print(f"  错误:              {stats['errors']} 篇")

    # 验证
    cursor.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''")
    has_abstract = cursor.fetchone()[0]
    print(f"\n✅ 最终有 abstract 的论文: {has_abstract}/{total}")

    conn.close()
    print("\n✅ 批量填充完成！")


if __name__ == "__main__":
    default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "research.db")
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db

    print("=" * 60)
    print("V25.18 批量填充：从已解析段落提取 abstract/affiliations/funding")
    print("=" * 60)
    print()

    backfill_paper_metadata(db_path)
