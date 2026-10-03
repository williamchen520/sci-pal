#!/usr/bin/env python3
"""
混合检索 V1.0

基于统一检索（unified_search.py），把关键词检索和向量检索的结果合并到一起。

使用方法：
  python services\search\hybrid_search_v2.py "STAT1 immunity"
"""

import argparse
import sqlite3
from pathlib import Path

from services.search.unified_search import UnifiedSearch


class HybridSearchV2:
    """混合检索 V2（基于统一检索）"""

    def __init__(self, unified_db: str, research_db: str, abstracts_db: str, xml_db: str):
        self.unified_search = UnifiedSearch(unified_db, research_db, abstracts_db, xml_db)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        混合检索

        Args:
            query: 检索关键词
            limit: 返回结果数量

        Returns:
            论文列表
        """
        # 第一步：用统一检索（unified_search.py）查联合索引（unified.db）
        results = self.unified_search.search_papers(query, limit)

        # 第二步：返回结果
        return results


def main():
    parser = argparse.ArgumentParser(description="混合检索 V2（基于统一检索）")
    parser.add_argument("query", type=str, help="检索关键词")
    parser.add_argument("--limit", type=int, default=10, help="返回结果数量")

    args = parser.parse_args()

    search = HybridSearchV2(
        unified_db="data/unified.db",
        research_db="data/research.db",
        abstracts_db="data/abstracts.db",
        xml_db="data/xml.db"
    )

    results = search.search(args.query, args.limit)

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
