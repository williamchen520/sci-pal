#!/usr/bin/env python3
"""
检索层 V1.0

把联合索引（unified.db）和三个数据库（research.db、abstracts.db、xml.db）接到下一层去。

使用方法：
  python services/search/unified_search.py
"""

import argparse
import sqlite3
from pathlib import Path


class UnifiedSearch:
    """统一检索层"""

    def __init__(self, unified_db: str, research_db: str, abstracts_db: str, xml_db: str):
        self.unified_db = unified_db
        self.research_db = research_db
        self.abstracts_db = abstracts_db
        self.xml_db = xml_db

    def search_papers(self, query: str, limit: int = 10) -> list[dict]:
        """
        检索论文

        Args:
            query: 检索关键词
            limit: 返回结果数量

        Returns:
            论文列表
        """
        # 第一步：查联合索引（unified.db）
        conn = sqlite3.connect(self.unified_db)
        cursor = conn.cursor()

        # 用 FTS5 全文检索（unified_papers_fts 表只有 paper_id、title、journal、abstract 字段）
        cursor.execute("""
            SELECT paper_id, title, journal, abstract
            FROM unified_papers_fts
            WHERE unified_papers_fts MATCH ?
            LIMIT ?
        """, (query, limit))

        rows = cursor.fetchall()
        conn.close()

        # 第二步：根据论文的 paper_id，去对应的数据库里面找具体的文章的结构信息
        results = []
        for row in rows:
            paper_id, title, journal, abstract = row

            # 从 unified_papers 表找 authors、publish_date、source_db
            conn = sqlite3.connect(self.unified_db)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT authors, publish_date, source_db
                FROM unified_papers
                WHERE paper_id = ?
            """, (paper_id,))
            paper_row = cursor.fetchone()
            conn.close()

            if paper_row:
                authors, publish_date, source_db = paper_row
            else:
                authors, publish_date, source_db = None, None, None

            # 找具体的文章的结构信息
            paragraphs = self._get_paragraphs(paper_id, source_db)

            results.append({
                "paper_id": paper_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "journal": journal,
                "publish_date": publish_date,
                "source_db": source_db,
                "paragraphs": paragraphs,
            })

        return results

    def _get_paragraphs(self, paper_id: str, source_db: str) -> list[dict]:
        """
        找具体的文章的结构信息（段落）

        Args:
            paper_id: 论文 ID
            source_db: 来源数据库

        Returns:
            段落列表
        """
        paragraphs = []

        if source_db == "research.db":
            conn = sqlite3.connect(self.research_db)
            cursor = conn.cursor()

            # 假设 research.db 有 paragraphs 表
            cursor.execute("""
                SELECT paragraph_index, text FROM paragraphs
                WHERE paper_id = ?
            """, (paper_id,))

            for row in cursor.fetchall():
                paragraph_index, text = row
                paragraphs.append({
                    "paragraph_index": paragraph_index,
                    "text": text,
                })

            conn.close()

        elif source_db == "abstracts.db":
            # abstracts.db 只有摘要，没有正文段落
            pass

        elif source_db == "xml.db":
            conn = sqlite3.connect(self.xml_db)
            cursor = conn.cursor()

            # 查正文段落
            cursor.execute("""
                SELECT section_title, paragraph_index, text FROM body_paragraphs
                WHERE paper_id = ?
            """, (paper_id,))

            for row in cursor.fetchall():
                section_title, paragraph_index, text = row
                paragraphs.append({
                    "section_title": section_title,
                    "paragraph_index": paragraph_index,
                    "text": text,
                })

            conn.close()

        return paragraphs


def main():
    parser = argparse.ArgumentParser(description="统一检索层")
    parser.add_argument("query", type=str, help="检索关键词")
    parser.add_argument("--limit", type=int, default=10, help="返回结果数量")

    args = parser.parse_args()

    search = UnifiedSearch(
        unified_db="data/unified.db",
        research_db="data/research.db",
        abstracts_db="data/abstracts.db",
        xml_db="data/xml.db"
    )

    results = search.search_papers(args.query, args.limit)

    print(f"\n{'='*60}")
    print(f"✅ 检索完成！")
    print(f"{'='*60}")
    print(f"  关键词: {args.query}")
    print(f"  返回结果: {len(results)} 篇论文")

    for i, paper in enumerate(results, 1):
        print(f"\n论文 {i}:")
        print(f"  标题: {paper['title']}")
        print(f"  作者: {paper['authors']}")
        print(f"  期刊: {paper['journal']}")
        print(f"  发表日期: {paper['publish_date']}")
        print(f"  来源数据库: {paper['source_db']}")
        print(f"  段落数: {len(paper['paragraphs'])}")


if __name__ == "__main__":
    main()
