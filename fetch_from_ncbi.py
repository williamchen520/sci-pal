
#!/usr/bin/env python3
"""
V25.18 从 NCBI PubMed 批量抓取论文元数据（abstract、authors、affiliations 等）

使用 NCBI E-utilities API（https://www.ncbi.nlm.nih.gov/books/NBK25500/）
- 优先用 DOI 查询
- DOI 查不到时用标题查询
- 自动处理速率限制（3次/秒，无 API key）
- 支持错误重试

用法:
  python3 fetch_from_ncbi.py [数据库路径]
  python3 fetch_from_ncbi.py data/research.db --api-key YOUR_NCBI_API_KEY

NCBI API key 申请（免费，可提高速率到10次/秒）:
  https://www.ncbi.nlm.nih.gov/account/settings/ -> API Key
"""


import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

# NCBI E-utilities 基础 URL
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def ncbi_request(url: str, retries: int = 3, delay: float = 0.5) -> str:
    """发送 NCBI API 请求，带重试和速率限制。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Sci-Pal/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < retries - 1:
                wait = delay * (2 ** attempt)
                print(f"    ⚠️  请求失败（{e}），{wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                raise
    return ""


def search_pubmed_by_doi(doi: str, api_key: str = "") -> str:
    """通过 DOI 搜索 PubMed，返回 PMID。"""
    if not doi:
        return ""
    # DOI 搜索：用 [doi] 标签
    term = urllib.parse.quote(f"{doi}[doi]")
    url = f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&term={term}&retmode=json"
    if api_key:
        url += f"&api_key={api_key}"
    result = ncbi_request(url)
    try:
        data = json.loads(result)
        id_list = data.get("esearchresult", {}).get("idlist", [])
        return id_list[0] if id_list else ""
    except Exception:
        return ""


def search_pubmed_by_title(title: str, api_key: str = "") -> str:
    """通过标题搜索 PubMed，返回 PMID。"""
    if not title or len(title) < 10:
        return ""
    # 标题搜索：用 [title] 标签
    term = urllib.parse.quote(f"{title}[title]")
    url = f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&term={term}&retmode=json&retmax=1"
    if api_key:
        url += f"&api_key={api_key}"
    result = ncbi_request(url)
    try:
        data = json.loads(result)
        id_list = data.get("esearchresult", {}).get("idlist", [])
        return id_list[0] if id_list else ""
    except Exception:
        return ""


def fetch_pubmed_metadata(pmid: str, api_key: str = "") -> dict:
    """通过 PMID 获取论文的完整元数据（XML 格式）。"""
    if not pmid:
        return {}
    url = f"{EUTILS_BASE}/efetch.fcgi?db=pubmed&id={pmid}&rettype=abstract&retmode=xml"
    if api_key:
        url += f"&api_key={api_key}"
    result = ncbi_request(url)
    return parse_pubmed_xml(result)


def parse_pubmed_xml(xml_text: str) -> dict:
    """解析 PubMed efetch 返回的 XML，提取元数据。"""
    metadata = {
        'title': '',
        'abstract': '',
        'authors': '',
        'affiliations': '',
        'journal': '',
        'year': None,
        'volume': '',
        'issue': '',
        'pages': '',
        'doi': '',
        'pmid': '',
    }
    if not xml_text:
        return metadata

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return metadata

    article = root.find(".//PubmedArticle/MedlineCitation/Article")
    if article is None:
        return metadata

    # PMID
    pmid_elem = root.find(".//PubmedArticle/MedlineCitation/PMID")
    if pmid_elem is not None and pmid_elem.text:
        metadata['pmid'] = pmid_elem.text

    # Title
    title_elem = article.find("ArticleTitle")
    if title_elem is not None and title_elem.text:
        metadata['title'] = title_elem.text

    # Abstract（可能有多个 AbstractText 段落）
    abstract_parts = []
    for abs_text in article.findall(".//Abstract/AbstractText"):
        label = abs_text.get("Label", "")
        text = "".join(abs_text.itertext()).strip()
        if text:
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
    metadata['abstract'] = " ".join(abstract_parts)

    # Authors
    author_list = []
    affiliation_list = []
    for author in article.findall(".//AuthorList/Author"):
        last = author.find("LastName")
        first = author.find("ForeName")
        initials = author.find("Initials")
        if last is not None and last.text:
            name = last.text
            if first is not None and first.text:
                name += f" {first.text}"
            elif initials is not None and initials.text:
                name += f" {initials.text}"
            author_list.append(name)
        # Affiliations
        for aff in author.findall(".//AffiliationInfo/Affiliation"):
            if aff.text and aff.text.strip():
                affiliation_list.append(aff.text.strip())
    metadata['authors'] = ", ".join(author_list)
    metadata['affiliations'] = "; ".join(list(dict.fromkeys(affiliation_list)))  # 去重保序

    # Journal
    journal_elem = article.find("Journal")
    if journal_elem is not None:
        title_elem = journal_elem.find("Title")
        if title_elem is not None and title_elem.text:
            metadata['journal'] = title_elem.text
        # Volume / Issue / Pages
        vol_elem = journal_elem.find("JournalIssue/Volume")
        if vol_elem is not None and vol_elem.text:
            metadata['volume'] = vol_elem.text
        issue_elem = journal_elem.find("JournalIssue/Issue")
        if issue_elem is not None and issue_elem.text:
            metadata['issue'] = issue_elem.text
        pages_elem = journal_elem.find("Pagination/MedlinePgn")
        if pages_elem is not None and pages_elem.text:
            metadata['pages'] = pages_elem.text
        # Year
        year_elem = journal_elem.find("JournalIssue/PubDate/Year")
        if year_elem is not None and year_elem.text:
            try:
                metadata['year'] = int(year_elem.text)
            except ValueError:
                pass

    # DOI（从 ELocationID 或 ArticleIdList）
    for eid in article.findall(".//ELocationID"):
        if eid.get("EIdType") == "doi" and eid.text:
            metadata['doi'] = eid.text
    if not metadata['doi']:
        for aid in root.findall(".//PubmedArticle/PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                metadata['doi'] = aid.text

    return metadata


def fetch_from_ncbi(db_path: str, api_key: str = "", delay: float = 0.35):
    """主函数：从 NCBI 批量抓取元数据并更新数据库。"""
    if not Path(db_path).exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    print(f"📂 数据库: {db_path}")
    if api_key:
        print(f"🔑 使用 NCBI API Key（速率 10次/秒）")
        delay = 0.11  # 10次/秒，留余量
    else:
        print(f"⚠️  未使用 NCBI API Key（速率 3次/秒，较慢）")
        print(f"    申请免费 API Key: https://www.ncbi.nlm.nih.gov/account/settings/")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取所有论文（优先处理没有 abstract 的）
    cursor.execute("""
        SELECT paper_id, title, doi, abstract
        FROM papers
        ORDER BY CASE WHEN abstract IS NULL OR abstract = '' THEN 0 ELSE 1 END, paper_id
    """)
    papers = cursor.fetchall()
    total = len(papers)

    print(f"📊 论文总数: {total}")
    no_abstract = sum(1 for p in papers if not p[3])
    print(f"   无 abstract: {no_abstract} 篇")
    print(f"   有 abstract: {total - no_abstract} 篇（跳过）")
    print()

    # 统计
    stats = {
        'found_by_doi': 0,
        'found_by_title': 0,
        'not_found': 0,
        'abstract_filled': 0,
        'affiliations_filled': 0,
        'skipped': 0,
        'errors': 0,
    }

    for idx, (paper_id, title, doi, existing_abstract) in enumerate(papers, 1):
        # 跳过已有 abstract 且长度足够的
        if existing_abstract and len(existing_abstract.strip()) > 50:
            stats['skipped'] += 1
            continue

        pmid = ""
        search_method = ""

        # 1. 优先用 DOI 搜索
        if doi:
            try:
                pmid = search_pubmed_by_doi(doi, api_key)
                if pmid:
                    search_method = "doi"
                    stats['found_by_doi'] += 1
            except Exception as e:
                print(f"  ⚠️  DOI 搜索出错: {e}")

        # 2. DOI 查不到，用标题搜索
        if not pmid and title:
            try:
                pmid = search_pubmed_by_title(title, api_key)
                if pmid:
                    search_method = "title"
                    stats['found_by_title'] += 1
            except Exception as e:
                print(f"  ⚠️  标题搜索出错: {e}")

        if not pmid:
            stats['not_found'] += 1
            if idx % 10 == 0 or idx == total:
                print(f"  [{idx}/{total}] 未找到: {title[:50]}...")
            time.sleep(delay)
            continue

        # 3. 获取完整元数据
        try:
            metadata = fetch_pubmed_metadata(pmid, api_key)
        except Exception as e:
            stats['errors'] += 1
            print(f"  ❌ [{idx}/{total}] 获取元数据失败: {title[:40]}... -> {e}")
            time.sleep(delay)
            continue

        # 4. 更新数据库
        update_fields = []
        update_values = []

        if metadata.get('abstract') and len(metadata['abstract']) > 20:
            update_fields.append("abstract = ?")
            update_values.append(metadata['abstract'][:5000])
            stats['abstract_filled'] += 1

        if metadata.get('affiliations') and not existing_abstract:
            # 只在没有 abstract 时更新 affiliations（避免覆盖已有数据）
            cursor.execute("SELECT affiliations FROM papers WHERE paper_id = ?", (paper_id,))
            existing_aff = cursor.fetchone()[0]
            if not existing_aff or len(existing_aff) < 10:
                update_fields.append("affiliations = ?")
                update_values.append(metadata['affiliations'][:5000])
                stats['affiliations_filled'] += 1

        if update_fields:
            update_values.append(paper_id)
            cursor.execute(
                f"UPDATE papers SET {', '.join(update_fields)} WHERE paper_id = ?",
                tuple(update_values)
            )
            conn.commit()

        if idx % 5 == 0 or idx == total:
            print(f"  [{idx}/{total}] ✓ ({search_method}) {title[:50]}...")

        time.sleep(delay)

    conn.close()

    # 最终统计
    print()
    print("=" * 60)
    print("📊 NCBI 抓取结果统计")
    print("=" * 60)
    print(f"  总论文数:          {total}")
    print(f"  跳过（已有abstract）: {stats['skipped']}")
    print(f"  DOI 搜索命中:      {stats['found_by_doi']}")
    print(f"  标题搜索命中:      {stats['found_by_title']}")
    print(f"  未找到:            {stats['not_found']}")
    print(f"  错误:              {stats['errors']}")
    print(f"  ─────────────────────────────")
    print(f"  填充 abstract:     {stats['abstract_filled']} 篇")
    print(f"  填充 affiliations: {stats['affiliations_filled']} 篇")

    # 验证最终 abstract 填充率
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''")
    has_abstract = cursor.fetchone()[0]
    print(f"\n✅ 最终有 abstract 的论文: {has_abstract}/{total}")
    conn.close()

    print("\n✅ NCBI 批量抓取完成！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 NCBI PubMed 批量抓取论文元数据")
    parser.add_argument("db_path", nargs="?", default="data/research.db", help="数据库路径")
    parser.add_argument("--api-key", default="", help="NCBI API Key（可选，提高速率）")
    args = parser.parse_args()

    print("=" * 60)
    print("V25.18 NCBI PubMed 元数据批量抓取")
    print("=" * 60)
    print()

    fetch_from_ncbi(args.db_path, args.api_key)
