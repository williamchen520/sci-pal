#!/usr/bin/env python3
"""
OpenAlex 批量下载脚本 V1.0

从 OpenAlex（免费 2 亿+ 学术论文）批量下载论文元数据和摘要。
OpenAlex 是完全免费的学术图谱，不需要 API key，覆盖所有学科。

功能：
1. 按关键词搜索下载论文元数据和摘要
2. 按期刊名搜索下载（定向扩充 Cell/Nature/Science 等顶刊）
3. 批量下载，支持断点续传
4. 输出为 JSONL 格式，方便后续导入 abstracts.db

使用方法：
  # 按关键词下载，每个关键词 500 篇
  python download_openalex.py --query "STAT1 interferon" --max 500

  # 按多个关键词批量下载
  python download_openalex.py --query "STAT1" --query "cancer immunology" --query "CRISPR" --max 300

  # 按期刊名定向下载（Cell 期刊近 5 年）
  python download_openalex.py --journal "Cell" --years 2021-2026 --max 1000

  # 批量下载多个顶刊
  python download_openalex.py --journal "Cell" --journal "Nature" --journal "Science" --years 2020-2026 --max 500

  # 指定输出文件
  python download_openalex.py --query "STAT1" --output data/openalex_stat1.jsonl

  # 断点续传（如果之前下载了一部分，继续下载）
  python download_openalex.py --query "STAT1" --output data/openalex_stat1.jsonl --resume
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# OpenAlex API 配置
OPENALEX_BASE = "https://api.openalex.org"
# 加 mailto 可以得到更快的速率限制（10 次/秒 vs 1 次/秒）
DEFAULT_MAILTO = "chenwei-ucas@outlook.com"

# 速率限制（秒/请求）
RATE_LIMIT = 0.2  # 5 次/秒，保守一点

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5

# 每次请求最多返回 200 条（OpenAlex 限制）
PER_PAGE = 200


def search_works(
    query: str = None,
    journal: str = None,
    years: str = None,
    page: int = 1,
    per_page: int = PER_PAGE,
    mailto: str = DEFAULT_MAILTO,
) -> dict:
    """
    搜索 OpenAlex works（论文）。

    Args:
        query: 搜索关键词
        journal: 期刊名
        years: 年份范围，如 "2020-2026"
        page: 页码
        per_page: 每页数量
        mailto: 邮箱（用于提速）

    Returns:
        OpenAlex API 返回的 JSON
    """
    params = {
        "page": page,
        "per-page": per_page,
    }
    if mailto:
        params["mailto"] = mailto

    # 构建过滤条件
    filters = []
    if years:
        # 年份范围，如 "2020-2026"
        parts = years.split("-")
        if len(parts) == 2:
            filters.append(f"from_publication_date:{parts[0]}-01-01")
            filters.append(f"to_publication_date:{parts[1]}-12-31")

    if journal:
        # 按期刊名搜索（OpenAlex 的期刊过滤需要期刊 ID，这里先用 search 搜索期刊）
        # 简化处理：把期刊名加到搜索关键词里
        pass

    if filters:
        params["filter"] = ",".join(filters)

    # 搜索关键词
    if query and journal:
        params["search"] = f"{query} {journal}"
    elif query:
        params["search"] = query
    elif journal:
        params["search"] = journal

    url = f"{OPENALEX_BASE}/works"

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                # 速率限制，等待后重试
                print(f"  ⏳ 速率限制，等待 {RETRY_DELAY} 秒后重试...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                print(f"  ⚠️  HTTP {resp.status_code}: {resp.text[:200]}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return {}
        except requests.RequestException as e:
            print(f"  ⚠️  请求失败: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return {}

    return {}


def parse_work(work: dict) -> dict:
    """
    解析 OpenAlex work 对象，提取我们需要的字段。

    Args:
        work: OpenAlex work JSON

    Returns:
        标准化的论文信息 dict
    """
    # 标题
    title = work.get("title", "")

    # 摘要（OpenAlex 的摘要在 abstract_inverted_index 里，需要还原）
    abstract = ""
    abstract_inv = work.get("abstract_inverted_index")
    if abstract_inv:
        # 还原摘要：从 inverted index 重建
        max_pos = max((max(positions) for positions in abstract_inv.values()), default=-1)
        if max_pos >= 0:
            words = [""] * (max_pos + 1)
            for word, positions in abstract_inv.items():
                for pos in positions:
                    if pos <= max_pos:
                        words[pos] = word
            abstract = " ".join(words)

    # 作者
    authors = []
    for auth in work.get("authorships", []):
        author_info = auth.get("author", {})
        authors.append({
            "name": author_info.get("display_name", ""),
            "id": author_info.get("id", ""),
            "orcid": author_info.get("orcid", ""),
        })

    # 期刊
    primary_location = work.get("primary_location", {})
    source = primary_location.get("source", {}) if primary_location else {}
    journal_name = source.get("display_name", "") if source else ""
    journal_id = source.get("id", "") if source else ""

    # 出版日期
    publication_date = work.get("publication_date", "")
    publication_year = work.get("publication_year", "")

    # DOI
    doi = work.get("doi", "")
    if doi:
        doi = doi.replace("https://doi.org/", "")

    # PMID（如果有的话）
    pmid = ""
    for ids in work.get("ids", {}):
        if ids == "pmid":
            pmid = work["ids"][ids]
            break

    # 引用数
    cited_by_count = work.get("cited_by_count", 0)

    # 概念标签（OpenAlex 的概念分类）
    concepts = []
    for concept in work.get("concepts", []):
        concepts.append({
            "name": concept.get("display_name", ""),
            "score": concept.get("score", 0),
            "id": concept.get("id", ""),
        })

    # 关键词
    keywords = []
    for kw in work.get("keywords", []):
        keywords.append(kw.get("display_name", ""))

    # OpenAlex ID
    openalex_id = work.get("id", "")
    if openalex_id:
        openalex_id = openalex_id.replace("https://openalex.org/", "")

    return {
        "id": f"openalex_{openalex_id}" if openalex_id else "",
        "openalex_id": openalex_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal_name,
        "journal_id": journal_id,
        "publication_date": publication_date,
        "publication_year": publication_year,
        "doi": doi,
        "pmid": pmid,
        "cited_by_count": cited_by_count,
        "concepts": concepts,
        "keywords": keywords,
        "source": "openalex",
    }


def download_batch(
    queries: list[str] = None,
    journals: list[str] = None,
    years: str = None,
    max_per_query: int = 200,
    output_file: str = "openalex_results.jsonl",
    resume: bool = False,
    mailto: str = DEFAULT_MAILTO,
):
    """
    批量下载 OpenAlex 论文。

    Args:
        queries: 搜索关键词列表
        journals: 期刊名列表
        years: 年份范围
        max_per_query: 每个关键词/期刊最多下载多少篇
        output_file: 输出文件路径（JSONL）
        resume: 是否断点续传
        mailto: 邮箱
    """
    # 确保输出目录存在
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 断点续传：读取已下载的 ID
    downloaded_ids = set()
    if resume and output_path.exists():
        print(f"📂 断点续传：读取已下载的记录...")
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get("id"):
                        downloaded_ids.add(record["id"])
                    if record.get("doi"):
                        downloaded_ids.add(f"doi_{record['doi']}")
                except json.JSONDecodeError:
                    continue
        print(f"  已下载 {len(downloaded_ids)} 条记录")

    # 构建搜索任务列表
    tasks = []
    if queries:
        for q in queries:
            tasks.append({"query": q, "journal": None, "label": f"关键词: {q}"})
    if journals:
        for j in journals:
            tasks.append({"query": None, "journal": j, "label": f"期刊: {j}"})

    if not tasks:
        print("❌ 没有指定搜索关键词或期刊名！")
        return

    print(f"🚀 开始批量下载，共 {len(tasks)} 个搜索任务，每个最多 {max_per_query} 篇")
    print(f"📝 输出文件: {output_file}")
    print()

    total_downloaded = 0
    total_skipped = 0

    with open(output_file, "a" if resume else "w", encoding="utf-8") as out_f:
        for task_idx, task in enumerate(tasks):
            query = task["query"]
            journal = task["journal"]
            label = task["label"]

            print(f"[{task_idx+1}/{len(tasks)}] {label}")

            # 计算需要多少页
            num_pages = (max_per_query + PER_PAGE - 1) // PER_PAGE
            task_downloaded = 0
            task_skipped = 0

            for page in range(1, num_pages + 1):
                if task_downloaded >= max_per_query:
                    break

                print(f"  📄 第 {page}/{num_pages} 页...", end=" ", flush=True)

                result = search_works(
                    query=query,
                    journal=journal,
                    years=years,
                    page=page,
                    per_page=PER_PAGE,
                    mailto=mailto,
                )

                works = result.get("results", [])
                total_count = result.get("meta", {}).get("count", 0)

                if not works:
                    print("没有更多结果")
                    break

                print(f"获取 {len(works)} 条（总计 {total_count} 条）")

                for work in works:
                    if task_downloaded >= max_per_query:
                        break

                    parsed = parse_work(work)

                    # 去重检查
                    record_id = parsed.get("id", "")
                    doi_id = f"doi_{parsed.get('doi', '')}" if parsed.get("doi") else ""

                    if record_id in downloaded_ids or (doi_id and doi_id in downloaded_ids):
                        task_skipped += 1
                        total_skipped += 1
                        continue

                    # 只保存有摘要的论文（没有摘要的对我们没用）
                    if not parsed.get("abstract"):
                        task_skipped += 1
                        total_skipped += 1
                        continue

                    # 写入文件
                    out_f.write(json.dumps(parsed, ensure_ascii=False) + "\n")
                    out_f.flush()

                    downloaded_ids.add(record_id)
                    if doi_id:
                        downloaded_ids.add(doi_id)

                    task_downloaded += 1
                    total_downloaded += 1

                # 速率限制
                time.sleep(RATE_LIMIT)

            print(f"  ✅ 本任务下载 {task_downloaded} 篇，跳过 {task_skipped} 篇")
            print()

    print(f"🎉 全部完成！")
    print(f"📊 总计下载: {total_downloaded} 篇")
    print(f"⏭️  总计跳过: {total_skipped} 篇（重复或无摘要）")
    print(f"📝 输出文件: {output_file}")
    print()
    print("💡 下一步：用 build_abstracts_db.py 把这些数据导入摘要数据库")


def main():
    parser = argparse.ArgumentParser(
        description="OpenAlex 批量下载脚本 - 免费 2 亿+ 学术论文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--query", "-q",
        action="append",
        help="搜索关键词（可多次指定）",
    )
    parser.add_argument(
        "--journal", "-j",
        action="append",
        help="期刊名（可多次指定，定向扩充特定期刊）",
    )
    parser.add_argument(
        "--years", "-y",
        type=str,
        default=None,
        help="年份范围，如 2020-2026",
    )
    parser.add_argument(
        "--max", "-m",
        type=int,
        default=200,
        help="每个关键词/期刊最多下载多少篇（默认 200）",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="data/openalex_results.jsonl",
        help="输出文件路径（JSONL 格式，默认 data/openalex_results.jsonl）",
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="断点续传（跳过已下载的记录）",
    )
    parser.add_argument(
        "--mailto",
        type=str,
        default=DEFAULT_MAILTO,
        help="邮箱（用于 OpenAlex 速率限制提速）",
    )

    args = parser.parse_args()

    if not args.query and not args.journal:
        parser.error("必须指定至少一个 --query 或 --journal！")

    download_batch(
        queries=args.query,
        journals=args.journal,
        years=args.years,
        max_per_query=args.max,
        output_file=args.output,
        resume=args.resume,
        mailto=args.mailto,
    )


if __name__ == "__main__":
    main()
