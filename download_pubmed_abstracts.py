#!/usr/bin/env python3
"""
PubMed 批量下载摘要脚本 V1.0

下载 PubMed 摘要（不是 PMC 全文），用来做摘要库。
- 按 8 个主题搜索
- 批量拉摘要（一次 100 个 PMID）
- 用 NCBI API key（速度更快）

使用方法：
  # 按关键词搜索下载摘要
  python download_pubmed_abstracts.py --query "STAT1 interferon"

  # 每个主题下载 200 篇
  python download_pubmed_abstracts.py --query "STAT1 interferon" --max 200

  # 批量跑所有 8 个主题
  python download_pubmed_abstracts.py --all-topics

  # 指定输出目录
  python download_pubmed_abstracts.py --query "STAT1 interferon" --output abstracts/
"""

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus

import requests

# 浏览器 User-Agent
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/xml,*/*",
}

# NCBI E-utilities 配置
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 工具标识（从 download_pmc_xml.py 复制过来的）
DEFAULT_TOOL = "scipal-pubmed-abstract-downloader"
DEFAULT_EMAIL = "chenwei-ucas@outlook.com"
DEFAULT_API_KEY = "76012a329673a2911604807c76294bf98507"

# 速率限制
RATE_LIMIT_NO_KEY = 0.35
RATE_LIMIT_WITH_KEY = 0.12

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5

# 8 个主题（从 download_100.bat 复制过来的）
TOPICS = [
    "STAT1 interferon",
    "breast cancer immunology",
    "liver disease fibrosis",
    "hepatitis B virus HBV",
    "bioinformatics single cell RNA sequencing",
    "innate immunity macrophage",
    "pediatric immunology children",
    "primary immunodeficiency disease",
]


def get_rate_limit():
    """根据有没有 API key 返回速率限制"""
    if DEFAULT_API_KEY:
        return RATE_LIMIT_WITH_KEY
    return RATE_LIMIT_NO_KEY


def build_url(endpoint, params):
    """构建 E-utilities URL"""
    base = f"{EUTILS_BASE}/{endpoint}.fcgi"
    params["tool"] = DEFAULT_TOOL
    params["email"] = DEFAULT_EMAIL
    if DEFAULT_API_KEY:
        params["api_key"] = DEFAULT_API_KEY
    query_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
    return f"{base}?{query_string}"


def esearch(query, retmax=100, retstart=0):
    """
    搜索 PubMed，返回 PMID 列表
    
    参数：
        query: 搜索关键词
        retmax: 最多返回多少个 PMID
        retstart: 从第几个开始（分页用）
    
    返回：
        PMID 列表
    """
    url = build_url("esearch", {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retstart": retstart,
        "retmode": "json",
    })
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            id_list = data.get("esearchresult", {}).get("idlist", [])
            return id_list
        except Exception as e:
            print(f"  ⚠️  搜索失败（尝试 {attempt+1}/{MAX_RETRIES}）: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    return []


def efetch_abstracts(pmid_list):
    """
    批量拉摘要
    
    参数：
        pmid_list: PMID 列表（一次最多 100 个）
    
    返回：
        摘要 XML
    """
    if not pmid_list:
        return None
    
    # 一次最多 100 个 PMID
    if len(pmid_list) > 100:
        pmid_list = pmid_list[:100]
    
    ids = ",".join(pmid_list)
    url = build_url("efetch", {
        "db": "pubmed",
        "id": ids,
        "rettype": "abstract",
        "retmode": "xml",
    })
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=BROWSER_HEADERS, timeout=60)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"  ⚠️  拉摘要失败（尝试 {attempt+1}/{MAX_RETRIES}）: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    return None


def parse_abstracts(xml_text):
    """
    解析摘要 XML，返回摘要列表
    
    返回：
        [
            {
                "pmid": "12345678",
                "title": "论文标题",
                "abstract": "摘要内容",
                "authors": "作者列表",
                "journal": "期刊名",
                "year": 2023,
            },
            ...
        ]
    """
    if not xml_text:
        return []
    
    root = ET.fromstring(xml_text)
    abstracts = []
    
    for article in root.findall(".//PubmedArticle"):
        # PMID
        pmid_elem = article.find(".//PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""
        
        # 标题
        title_elem = article.find(".//ArticleTitle")
        title = "".join(title_elem.itertext()) if title_elem is not None else ""
        
        # 摘要
        abstract_parts = []
        for abstract_elem in article.findall(".//AbstractText"):
            # 处理摘要小标题（如 "Background:", "Methods:"）
            label = abstract_elem.get("Label")
            text = "".join(abstract_elem.itertext())
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = "\n".join(abstract_parts)
        
        # 作者
        authors = []
        for author in article.findall(".//Author"):
            last_name = author.find("LastName")
            fore_name = author.find("ForeName")
            if last_name is not None and fore_name is not None:
                authors.append(f"{fore_name.text} {last_name.text}")
            elif last_name is not None:
                authors.append(last_name.text)
        authors_str = "; ".join(authors)
        
        # 期刊
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else ""
        
        # 年份
        year_elem = article.find(".//PubDate/Year")
        year = int(year_elem.text) if year_elem is not None else None
        
        # DOI
        doi = ""
        for article_id in article.findall(".//ArticleId"):
            if article_id.get("IdType") == "doi":
                doi = article_id.text or ""
                break
        
        abstracts.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors_str,
            "journal": journal,
            "year": year,
            "doi": doi,
        })
    
    return abstracts


def download_topic(topic, max_papers=200, output_dir="abstracts"):
    """
    下载一个主题的所有摘要
    
    参数：
        topic: 主题关键词
        max_papers: 最多下载多少篇
        output_dir: 输出目录
    """
    print(f"\n📥 下载主题: {topic}")
    print("=" * 60)
    
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 搜索 PMID
    print(f"  🔍 搜索中...")
    all_pmids = []
    retstart = 0
    batch_size = 100
    
    while len(all_pmids) < max_papers:
        pmids = esearch(topic, retmax=batch_size, retstart=retstart)
        if not pmids:
            break
        all_pmids.extend(pmids)
        print(f"    找到 {len(all_pmids)} 个 PMID")
        retstart += batch_size
        time.sleep(get_rate_limit())
    
    print(f"  ✅ 总共找到 {len(all_pmids)} 个 PMID")
    
    # 批量拉摘要
    all_abstracts = []
    for i in range(0, len(all_pmids), 100):
        batch = all_pmids[i:i+100]
        print(f"  📄 拉摘要 {i+1}-{i+len(batch)}...")
        xml_text = efetch_abstracts(batch)
        if xml_text:
            abstracts = parse_abstracts(xml_text)
            all_abstracts.extend(abstracts)
            print(f"    解析出 {len(abstracts)} 篇摘要")
        time.sleep(get_rate_limit())
    
    print(f"  ✅ 总共解析出 {len(all_abstracts)} 篇摘要")
    
    # 保存到 JSON 文件
    output_file = output_path / f"{topic.replace(' ', '_')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_abstracts, f, ensure_ascii=False, indent=2)
    
    print(f"  💾 保存到: {output_file}")
    
    return all_abstracts


def main():
    parser = argparse.ArgumentParser(description="PubMed 批量下载摘要")
    parser.add_argument("--query", type=str, help="搜索关键词")
    parser.add_argument("--max", type=int, default=200, help="最多下载多少篇（默认 200）")
    parser.add_argument("--output", type=str, default="abstracts_xml", help="输出目录（默认 abstracts_xml）")
    parser.add_argument("--all-topics", action="store_true", help="批量跑所有 8 个主题")
    
    args = parser.parse_args()
    
    print("📥 PubMed 批量下载摘要 V1.0")
    print("=" * 60)
    
    if args.all_topics:
        # 批量跑所有主题
        for topic in TOPICS:
            download_topic(topic, max_papers=args.max, output_dir=args.output)
    elif args.query:
        # 跑单个主题
        download_topic(args.query, max_papers=args.max, output_dir=args.output)
    else:
        print("用法:")
        print("  python download_pubmed_abstracts.py --query 'STAT1 interferon'")
        print("  python download_pubmed_abstracts.py --all-topics")
        print("  python download_pubmed_abstracts.py --query 'STAT1 interferon' --max 500")


if __name__ == "__main__":
    main()
