#!/usr/bin/env python3
"""
V25.18 Zotero 元数据导入脚本
从 Zotero 导出的 CSL JSON 文件中提取元数据，批量更新到 Sci-Pal papers 表。

匹配策略：
1. 优先用 DOI 精确匹配（最准确）
2. DOI 匹配不到的，用标题归一化后模糊匹配

更新字段：
- title, authors, journal, doi, year, volume, issue, pages
- abstract, paper_type, publisher, language, keywords
- parse_engine 标记为 'zotero_import'
"""

import json
import sqlite3
import sys
import os
import re
from datetime import datetime


def normalize_title(title):
    """标题归一化：去掉标点、空格、大小写，用于模糊匹配"""
    if not title:
        return ''
    # 去掉 HTML 标签
    title = re.sub(r'<[^>]+>', '', title)
    # 只保留字母和数字，去掉所有标点和空格
    title = re.sub(r'[^a-zA-Z0-9]', '', title)
    return title.lower()


def normalize_doi(doi):
    """DOI 归一化：去掉 URL 前缀，转小写"""
    if not doi:
        return ''
    doi = doi.strip()
    # 去掉常见的 URL 前缀
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = re.sub(r'^doi:', '', doi, flags=re.IGNORECASE)
    return doi.lower().strip()


def format_authors(authors_list):
    """将 CSL JSON 的作者数组格式化为字符串"""
    if not authors_list:
        return ''
    names = []
    for author in authors_list:
        if isinstance(author, dict):
            family = author.get('family', '')
            given = author.get('given', '')
            if family and given:
                names.append(f"{family} {given}")
            elif family:
                names.append(family)
            elif given:
                names.append(given)
            elif 'literal' in author:
                names.append(author['literal'])
        elif isinstance(author, str):
            names.append(author)
    return '; '.join(names)


def extract_year(issued):
    """从 CSL JSON 的 issued 字段提取年份"""
    if not issued:
        return None
    if isinstance(issued, dict):
        date_parts = issued.get('date-parts', [])
        if date_parts and len(date_parts) > 0:
            year = date_parts[0][0] if date_parts[0] else None
            return year
        # 有些用 raw 字段
        raw = issued.get('raw', '')
        if raw:
            match = re.search(r'\b(19|20)\d{2}\b', raw)
            if match:
                return int(match.group())
    return None


def clean_text(text):
    """清理文本中的 HTML 标签和多余空白"""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def import_zotero_metadata(json_path, db_path):
    print("=" * 70)
    print("📥 V25.18 Zotero 元数据导入")
    print("=" * 70)
    print(f"📂 Zotero 导出文件: {json_path}")
    print(f"🗄️  Sci-Pal 数据库: {db_path}")

    if not os.path.exists(json_path):
        print(f"❌ JSON 文件不存在: {json_path}")
        return

    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        return

    # ── 1. 读取 CSL JSON ──
    print("\n── 1. 读取 Zotero 导出文件 ──")
    with open(json_path, 'r', encoding='utf-8') as f:
        zotero_items = json.load(f)

    if not isinstance(zotero_items, list):
        # 有些导出可能是单个对象
        zotero_items = [zotero_items]

    print(f"   Zotero 文献总数: {len(zotero_items)}")

    # ── 2. 连接数据库 ──
    print("\n── 2. 连接 Sci-Pal 数据库 ──")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 检查 papers 表结构
    cursor.execute("PRAGMA table_info(papers)")
    columns = {row['name'] for row in cursor.fetchall()}
    print(f"   papers 表字段数: {len(columns)}")

    # 获取 Sci-Pal 所有论文
    cursor.execute("SELECT paper_id, title, doi FROM papers")
    scipal_papers = cursor.fetchall()
    print(f"   Sci-Pal 论文总数: {len(scipal_papers)}")

    # 建立 DOI 索引和标题索引
    doi_index = {}  # normalized_doi -> paper_id
    title_index = {}  # normalized_title -> paper_id
    for row in scipal_papers:
        paper_id = row['paper_id']
        doi = normalize_doi(row['doi'])
        title = normalize_title(row['title'])
        if doi:
            doi_index[doi] = paper_id
        if title:
            title_index[title] = paper_id

    print(f"   DOI 索引: {len(doi_index)} 条")
    print(f"   标题索引: {len(title_index)} 条")

    # ── 3. 遍历 Zotero 文献，匹配并更新 ──
    print("\n── 3. 匹配并更新元数据 ──")

    stats = {
        'total': len(zotero_items),
        'doi_matched': 0,
        'title_matched': 0,
        'not_matched': 0,
        'updated_fields': {
            'title': 0,
            'authors': 0,
            'journal': 0,
            'doi': 0,
            'year': 0,
            'volume': 0,
            'issue': 0,
            'pages': 0,
            'abstract': 0,
            'publisher': 0,
            'language': 0,
            'paper_type': 0,
        },
        'abstract_filled': 0,
    }

    not_matched_items = []

    for idx, item in enumerate(zotero_items, 1):
        # 提取元数据
        zotero_doi = normalize_doi(item.get('DOI', ''))
        zotero_title = clean_text(item.get('title', ''))
        zotero_title_norm = normalize_title(zotero_title)
        zotero_authors = format_authors(item.get('author', []))
        zotero_journal = clean_text(item.get('container-title', ''))
        zotero_year = extract_year(item.get('issued'))
        zotero_volume = item.get('volume', '')
        zotero_issue = item.get('issue', '')
        zotero_pages = item.get('page', '')
        zotero_abstract = clean_text(item.get('abstract', ''))
        zotero_publisher = clean_text(item.get('publisher', ''))
        zotero_language = item.get('language', '')
        zotero_type = item.get('type', '')
        zotero_keywords = item.get('keyword', '')

        # 匹配策略：先 DOI，后标题
        matched_paper_id = None
        match_method = None

        if zotero_doi and zotero_doi in doi_index:
            matched_paper_id = doi_index[zotero_doi]
            match_method = 'DOI'
            stats['doi_matched'] += 1
        elif zotero_title_norm and zotero_title_norm in title_index:
            matched_paper_id = title_index[zotero_title_norm]
            match_method = '标题'
            stats['title_matched'] += 1
        else:
            stats['not_matched'] += 1
            not_matched_items.append({
                'idx': idx,
                'title': zotero_title[:60],
                'doi': zotero_doi,
            })
            continue

        # 构建更新字段
        update_fields = {}
        update_values = []

        # 只在 Sci-Pal 字段为空或更短的时候更新（Zotero 的元数据通常更完整）
        # 但 title 始终用 Zotero 的（更规范）
        if zotero_title:
            update_fields['title = ?'] = zotero_title
            stats['updated_fields']['title'] += 1

        if zotero_authors:
            update_fields['authors = ?'] = zotero_authors
            stats['updated_fields']['authors'] += 1

        if zotero_journal:
            update_fields['journal = ?'] = zotero_journal
            stats['updated_fields']['journal'] += 1

        if zotero_doi:
            update_fields['doi = ?'] = zotero_doi
            stats['updated_fields']['doi'] += 1

        if zotero_year:
            update_fields['year = ?'] = zotero_year
            stats['updated_fields']['year'] += 1

        if zotero_volume and 'volume' in columns:
            update_fields['volume = ?'] = zotero_volume
            stats['updated_fields']['volume'] += 1

        if zotero_issue and 'issue' in columns:
            update_fields['issue = ?'] = zotero_issue
            stats['updated_fields']['issue'] += 1

        if zotero_pages and 'pages' in columns:
            update_fields['pages = ?'] = zotero_pages
            stats['updated_fields']['pages'] += 1

        if zotero_abstract and 'abstract' in columns:
            update_fields['abstract = ?'] = zotero_abstract
            stats['updated_fields']['abstract'] += 1
            stats['abstract_filled'] += 1

        if zotero_publisher and 'publisher' in columns:
            update_fields['publisher = ?'] = zotero_publisher
            stats['updated_fields']['publisher'] += 1

        if zotero_language and 'language' in columns:
            update_fields['language = ?'] = zotero_language
            stats['updated_fields']['language'] += 1

        if zotero_type and 'paper_type' in columns:
            # CSL type 映射到我们的 paper_type
            type_map = {
                'article-journal': 'J',
                'article': 'J',
                'book': 'B',
                'chapter': 'C',
                'paper-conference': 'C',
                'thesis': 'T',
                'report': 'R',
                'review': 'R',
            }
            mapped_type = type_map.get(zotero_type, 'J')
            update_fields['paper_type = ?'] = mapped_type
            stats['updated_fields']['paper_type'] += 1

        # 更新 parse_engine 和 updated_at
        if 'parse_engine' in columns:
            update_fields['parse_engine = ?'] = 'zotero_import'
        if 'updated_at' in columns:
            update_fields['updated_at = ?'] = datetime.now().isoformat()

        # 执行更新
        if update_fields:
            set_clause = ', '.join(update_fields.keys())
            update_values = list(update_fields.values())
            update_values.append(matched_paper_id)

            query = f"UPDATE papers SET {set_clause} WHERE paper_id = ?"
            cursor.execute(query, update_values)

        # 打印进度
        if idx % 10 == 0 or idx == len(zotero_items):
            print(f"   进度: {idx}/{len(zotero_items)} (DOI匹配: {stats['doi_matched']}, 标题匹配: {stats['title_matched']}, 未匹配: {stats['not_matched']})")

    conn.commit()

    # ── 4. 汇总统计 ──
    print("\n" + "=" * 70)
    print("📊 导入结果统计")
    print("=" * 70)
    print(f"  Zotero 文献总数:      {stats['total']}")
    print(f"  ✅ DOI 精确匹配:       {stats['doi_matched']} 篇")
    print(f"  ✅ 标题模糊匹配:       {stats['title_matched']} 篇")
    print(f"  ❌ 未匹配:             {stats['not_matched']} 篇")
    print(f"  ─────────────────────────────")
    print(f"  📝 填充摘要(abstract): {stats['abstract_filled']} 篇")
    print(f"  ─────────────────────────────")
    print(f"  字段更新统计:")
    for field, count in stats['updated_fields'].items():
        if count > 0:
            print(f"    {field}: {count} 篇")

    # 未匹配的文献
    if not_matched_items:
        print(f"\n⚠️  未匹配的文献（共 {len(not_matched_items)} 篇）:")
        for item in not_matched_items[:20]:  # 最多显示20条
            print(f"   [{item['idx']}] {item['title']}")
            if item['doi']:
                print(f"        DOI: {item['doi']}")
        if len(not_matched_items) > 20:
            print(f"   ... 还有 {len(not_matched_items) - 20} 篇未显示")

    # ── 5. 验证：更新后有 abstract 的论文数 ──
    print("\n── 4. 验证：更新后 abstract 填充情况 ──")
    cursor.execute("SELECT COUNT(*) as cnt FROM papers WHERE abstract IS NOT NULL AND abstract != ''")
    abstract_count = cursor.fetchone()['cnt']
    cursor.execute("SELECT COUNT(*) as cnt FROM papers")
    total_count = cursor.fetchone()['cnt']
    print(f"   有 abstract 的论文: {abstract_count}/{total_count} ({abstract_count/total_count*100:.1f}%)")

    conn.close()
    print("\n" + "=" * 70)
    print("✅ Zotero 元数据导入完成！")
    print("=" * 70)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 import_zotero_metadata.py <Zotero JSON路径> [Sci-Pal数据库路径]")
        print("示例: python3 import_zotero_metadata.py data/zotero_export.json data/research.db")
        sys.exit(1)

    json_path = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else 'data/research.db'

    import_zotero_metadata(json_path, db_path)
