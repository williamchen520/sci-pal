#!/usr/bin/env python3
"""
批量解析 PMC 全文 XML，建独立数据库 V1.0

使用方法：
  python scripts\build_xml_db.py
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# 导入解析函数
sys.path.insert(0, str(Path(__file__).parent))
from parse_pmc_xml import parse_pmc_xml


def create_database(db_path: str):
    """创建数据库表结构"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 论文表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pmcid TEXT UNIQUE,
            pmid TEXT,
            doi TEXT,
            title TEXT
        )
    """)

    # 摘要段落表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abstract_paragraphs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            paragraph_index INTEGER,
            text TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    # 正文段落表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS body_paragraphs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            section_title TEXT,
            section_level INTEGER,
            paragraph_index INTEGER,
            text TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    # 句子表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            paragraph_type TEXT,  -- 'abstract' or 'body'
            paragraph_id INTEGER,
            sentence_index INTEGER,
            text TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    # 参考文献表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            ref_id TEXT,
            text TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    conn.commit()
    conn.close()


def insert_paper(conn, result: dict):
    """插入一篇论文"""
    cursor = conn.cursor()

    # 插入论文
    cursor.execute("""
        INSERT OR REPLACE INTO papers (pmcid, pmid, doi, title)
        VALUES (?, ?, ?, ?)
    """, (
        result['pmcid'],
        result['pmid'],
        result['doi'],
        result['title']
    ))

    paper_id = cursor.lastrowid

    # 插入摘要段落
    for i, p in enumerate(result['abstract']):
        cursor.execute("""
            INSERT INTO abstract_paragraphs (paper_id, paragraph_index, text)
            VALUES (?, ?, ?)
        """, (paper_id, i, p['text']))

        para_id = cursor.lastrowid

        # 插入句子
        for j, sent in enumerate(p['sentences']):
            cursor.execute("""
                INSERT INTO sentences (paper_id, paragraph_type, paragraph_id, sentence_index, text)
                VALUES (?, ?, ?, ?, ?)
            """, (paper_id, 'abstract', para_id, j, sent))

    # 插入正文章节和段落
    for sec in result['body']:
        for i, p in enumerate(sec['paragraphs']):
            cursor.execute("""
                INSERT INTO body_paragraphs (paper_id, section_title, section_level, paragraph_index, text)
                VALUES (?, ?, ?, ?, ?)
            """, (paper_id, sec['title'], sec['level'], i, p['text']))

            para_id = cursor.lastrowid

            # 插入句子
            for j, sent in enumerate(p['sentences']):
                cursor.execute("""
                    INSERT INTO sentences (paper_id, paragraph_type, paragraph_id, sentence_index, text)
                    VALUES (?, ?, ?, ?, ?)
                """, (paper_id, 'body', para_id, j, sent))

    # 插入参考文献
    for ref in result['references']:
        cursor.execute("""
            INSERT INTO references (paper_id, ref_id, text)
            VALUES (?, ?, ?)
        """, (paper_id, ref['id'], ref['text']))

    conn.commit()
    return paper_id


def main():
    parser = argparse.ArgumentParser(description="批量解析 PMC 全文 XML，建独立数据库")
    parser.add_argument("--input-dir", type=str, default="documents_xml", help="XML 文件目录")
    parser.add_argument("--db-path", type=str, default="data/xml.db", help="数据库路径")

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    db_path = Path(args.db_path)

    # 创建数据库目录
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建数据库表结构
    create_database(str(db_path))

    # 找到所有 XML 文件
    xml_files = list(input_dir.glob("*.xml"))
    print(f"📄 找到 {len(xml_files)} 个 XML 文件")

    # 批量解析并插入数据库
    conn = sqlite3.connect(str(db_path))

    success = 0
    failed = 0

    for i, xml_file in enumerate(xml_files, 1):
        print(f"\n[{i}/{len(xml_files)}] 解析: {xml_file.name}")

        try:
            result = parse_pmc_xml(str(xml_file))
            paper_id = insert_paper(conn, result)
            print(f"  ✅ 插入成功，paper_id={paper_id}")
            success += 1
        except Exception as e:
            print(f"  ❌ 解析失败: {e}")
            failed += 1

    conn.close()

    # 打印统计
    print(f"\n{'='*60}")
    print(f"✅ 完成！")
    print(f"{'='*60}")
    print(f"  成功: {success}")
    print(f"  失败: {failed}")
    print(f"  数据库: {db_path}")


if __name__ == "__main__":
    main()
