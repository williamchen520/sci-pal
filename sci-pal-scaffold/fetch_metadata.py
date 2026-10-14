#!/usr/bin/env python3
"""
V25.18 从 NCBI PubMed + Crossref 批量抓取论文元数据（abstract、authors、affiliations 等）

双引擎策略：
1. 优先用 NCBI PubMed（生物医学论文，abstract 质量高）
   - 优先 DOI 搜索，查不到用标题搜索
2. NCBI 查不到的，自动 fallback 到 Crossref（覆盖所有有 DOI 的论文）
   - 通过 DOI 直接查询，不需要 API key
   - 速率限制 50次/秒（匿名）

两个 API 都不需要账号密码，匿名即可使用。

用法:
  python3 fetch_metadata.py [数据库路径]
  python3 fetch_metadata.py data/research.db --api-key YOUR_NCBI_API_KEY

NCBI API key 申请（免费，可提高 NCBI 速率到10次/秒）:
  https://www.ncbi.nlm.nih.gov/account/settings/ -> API Key
"""

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

# NCBI E-utilities 基础 URL
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# Crossref API 基础 URL
CROSSREF_BASE = "https://api.crossref.org/works"


def http_request(url: str, retries: int = 3, delay: float = 0.5, timeout: int = 30) -> str:
    """发送 HTTP 请求，带重试。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Sci-Pal/1.0 (mailto:scipal@example.com)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < retries - 1:
                wait = delay * (2 ** attempt)
                print(f"    ⚠️  请求失败（{e}），{wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                raise
    return ""


# ═══════════════════════════════════════════════════════════════
# NCBI PubMed 相关函数
# ═══════════════════════════════════════════════════════════════

def search_pubmed_by_doi(doi: str, api_key: str = "") -> str:
    """通过 DOI 搜索 PubMed，返回 PMID。"""
    if not doi:
        return ""
    term = urllib.parse.quote(f"{doi}[doi]")
    url = f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&term={term}&retmode=json"
    if api_key:
        url += f"&api_key={api_key}"
    result = http_request(url)
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
    term = urllib.parse.quote(f"{title}[title]")
    url = f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&term={term}&retmode=json&retmax=1"
    if api_key:
        url += f"&api_key={api_key}"
    result = http_request(url)
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
    result = http_request(url)
    return parse_pubmed_xml(result)


def parse_pubmed_xml(xml_text: str) -> dict:
    """解析 PubMed efetch 返回的 XML，提取元数据。"""
    metadata = {
        'title': '', 'abstract': '', 'authors': '', 'affiliations': '',
        'journal': '', 'year': None, 'volume': '', 'issue': '',
        'pages': '', 'doi': '', 'pmid': '',
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

    pmid_elem = root.find(".//PubmedArticle/MedlineCitation/PMID")
    if pmid_elem is not None and pmid_elem.text:
        metadata['pmid'] = pmid_elem.text

    title_elem = article.find("ArticleTitle")
    if title_elem is not None and title_elem.text:
        metadata['title'] = title_elem.text

    # Abstract（可能有多个 AbstractText 段落）
    abstract_parts = []
    for abs_text in article.findall(".//Abstract/AbstractText"):
        label = abs_text.get("Label", "")
        text = "".join(abs_text.itertext()).strip()
        if text:
            abstract_parts.append(f"{label}: {text}" if label else text)
    metadata['abstract'] = " ".join(abstract_parts)

    # Authors + Affiliations
    author_list = []
    affiliation_list = []
    for author in article.findall(".//AuthorList/Author"):
        last = author.find("LastName")
        first = author.find("ForeName")
        if last is not None and last.text:
            name = last.text + (f" {first.text}" if first is not None and first.text else "")
            author_list.append(name)
        for aff in author.findall(".//AffiliationInfo/Affiliation"):
            if aff.text and aff.text.strip():
                affiliation_list.append(aff.text.strip())
    metadata['authors'] = ", ".join(author_list)
    metadata['affiliations'] = "; ".join(list(dict.fromkeys(affiliation_list)))

    # Journal
    journal_elem = article.find("Journal")
    if journal_elem is not None:
        jt = journal_elem.find("Title")
        if jt is not None and jt.text:
            metadata['journal'] = jt.text
        vol = journal_elem.find("JournalIssue/Volume")
        if vol is not None and vol.text:
            metadata['volume'] = vol.text
        issue = journal_elem.find("JournalIssue/Issue")
        if issue is not None and issue.text:
            metadata['issue'] = issue.text
        pages = journal_elem.find("Pagination/MedlinePgn")
        if pages is not None and pages.text:
            metadata['pages'] = pages.text
        year = journal_elem.find("JournalIssue/PubDate/Year")
        if year is not None and year.text:
            try:
                metadata['year'] = int(year.text)
            except ValueError:
                pass

    # DOI
    for eid in article.findall(".//ELocationID"):
        if eid.get("EIdType") == "doi" and eid.text:
            metadata['doi'] = eid.text
    if not metadata['doi']:
        for aid in root.findall(".//PubmedArticle/PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                metadata['doi'] = aid.text

    return metadata


# ═══════════════════════════════════════════════════════════════
# Crossref 相关函数
# ═══════════════════════════════════════════════════════════════

def clean_crossref_abstract(abstract_html: str) -> str:
    """清洗 Crossref 返回的 abstract（包含 JATS XML 标签）。"""
    if not abstract_html:
        return ""
    # 去掉 JATS 命名空间标签，如 <jats:p>、<jats:title>、<jats:sec> 等
    text = re.sub(r'</?jats:[^>]*>', '', abstract_html)
    # 去掉其他可能的 XML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 去掉多余的空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fetch_crossref_metadata(doi: str) -> dict:
    """通过 DOI 从 Crossref 获取论文元数据。"""
    if not doi:
        return {}
    # DOI 可能包含特殊字符，需要 URL 编码
    encoded_doi = urllib.parse.quote(doi, safe='')
    url = f"{CROSSREF_BASE}/{encoded_doi}"
    try:
        result = http_request(url, retries=2, delay=0.3)
        data = json.loads(result)
        message = data.get('message', {})
    except Exception:
        return {}

    metadata = {
        'title': '', 'abstract': '', 'authors': '', 'affiliations': '',
        'journal': '', 'year': None, 'volume': '', 'issue': '',
        'pages': '', 'doi': doi, 'pmid': '',
    }

    # Title
    titles = message.get('title', [])
    if titles:
        metadata['title'] = titles[0]

    # Abstract（需要清洗 JATS 标签）
    raw_abstract = message.get('abstract', '')
    if raw_abstract:
        metadata['abstract'] = clean_crossref_abstract(raw_abstract)

    # Authors
    author_list = []
    for author in message.get('author', []):
        given = author.get('given', '')
        family = author.get('family', '')
        name = f"{family} {given}".strip()
        if name:
            author_list.append(name)
    metadata['authors'] = ", ".join(author_list)

    # Journal
    containers = message.get('container-title', [])
    if containers:
        metadata['journal'] = containers[0]

    # Volume / Issue / Pages
    metadata['volume'] = message.get('volume', '') or ''
    metadata['issue'] = message.get('issue', '') or ''
    metadata['pages'] = message.get('page', '') or ''

    # Year
    published = message.get('published-print', {}) or message.get('published-online', {}) or message.get('issued', {})
    date_parts = published.get('date-parts', [])
    if date_parts and date_parts[0]:
        try:
            metadata['year'] = int(date_parts[0][0])
        except (ValueError, IndexError):
            pass

    return metadata


def title_similarity(title1: str, title2: str) -> float:
    """计算两个标题的相似度（单词重叠度，0.0 ~ 1.0）。"""
    if not title1 or not title2:
        return 0.0
    # 转小写，去掉标点，拆成单词集合
    def normalize(t):
        t = t.lower()
        t = re.sub(r'[^\w\s]', ' ', t)
        words = set(t.split())
        # 去掉太短的词（1-2个字母）
        return {w for w in words if len(w) > 2}
    words1 = normalize(title1)
    words2 = normalize(title2)
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


def search_crossref_by_title(title: str, min_similarity: float = 0.6) -> dict:
    """通过标题搜索 Crossref，返回最匹配的论文元数据。

    用 query.bibliographic 搜索，取第一个结果，比较标题相似度。
    相似度 >= min_similarity 才认为匹配成功。
    """
    if not title or len(title) < 10:
        return {}
    query = urllib.parse.quote(title)
    url = f"{CROSSREF_BASE}?query.bibliographic={query}&rows=3&select=DOI,title,abstract,author,container-title,volume,issue,page,published-print,published-online,issued"
    try:
        result = http_request(url, retries=2, delay=0.3)
        data = json.loads(result)
        items = data.get('message', {}).get('items', [])
    except Exception:
        return {}

    if not items:
        return {}

    # 在前3个结果中找相似度最高的
    best_item = None
    best_sim = 0.0
    for item in items:
        item_titles = item.get('title', [])
        if not item_titles:
            continue
        sim = title_similarity(title, item_titles[0])
        if sim > best_sim:
            best_sim = sim
            best_item = item

    if not best_item or best_sim < min_similarity:
        return {}

    # 解析匹配到的结果（复用 parse_crossref_item 的逻辑）
    return parse_crossref_item(best_item)


def parse_crossref_item(item: dict) -> dict:
    """解析 Crossref 搜索结果中的单个 item，提取元数据。"""
    metadata = {
        'title': '', 'abstract': '', 'authors': '', 'affiliations': '',
        'journal': '', 'year': None, 'volume': '', 'issue': '',
        'pages': '', 'doi': '', 'pmid': '',
    }

    titles = item.get('title', [])
    if titles:
        metadata['title'] = titles[0]

    raw_abstract = item.get('abstract', '')
    if raw_abstract:
        metadata['abstract'] = clean_crossref_abstract(raw_abstract)

    author_list = []
    for author in item.get('author', []):
        given = author.get('given', '')
        family = author.get('family', '')
        name = f"{family} {given}".strip()
        if name:
            author_list.append(name)
    metadata['authors'] = ", ".join(author_list)

    containers = item.get('container-title', [])
    if containers:
        metadata['journal'] = containers[0]

    metadata['volume'] = item.get('volume', '') or ''
    metadata['issue'] = item.get('issue', '') or ''
    metadata['pages'] = item.get('page', '') or ''
    metadata['doi'] = item.get('DOI', '') or ''

    published = item.get('published-print', {}) or item.get('published-online', {}) or item.get('issued', {})
    date_parts = published.get('date-parts', [])
    if date_parts and date_parts[0]:
        try:
            metadata['year'] = int(date_parts[0][0])
        except (ValueError, IndexError):
            pass

    return metadata


# ═══════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════

def fetch_metadata(db_path: str, api_key: str = ""):
    """主函数：NCBI + Crossref 双引擎批量抓取元数据。"""
    if not Path(db_path).exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    print(f"📂 数据库: {db_path}")
    if api_key:
        print(f"🔑 使用 NCBI API Key（NCBI 速率 10次/秒）")
        ncbi_delay = 0.11
    else:
        print(f"ℹ️  未使用 NCBI API Key（NCBI 速率 3次/秒）")
        ncbi_delay = 0.35
    print(f"ℹ️  Crossref 速率 50次/秒（匿名，无需 key）")
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
        'ncbi_doi': 0,          # NCBI DOI 搜索命中
        'ncbi_title': 0,        # NCBI 标题搜索命中
        'crossref_doi': 0,      # Crossref DOI 查询命中
        'crossref_title': 0,    # Crossref 标题搜索命中
        'not_found': 0,          # 所有引擎都没找到
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
        metadata = {}
        source = ""

        # ── 第一引擎：NCBI PubMed ──
        # 1a. 优先用 DOI 搜索
        if doi:
            try:
                pmid = search_pubmed_by_doi(doi, api_key)
                if pmid:
                    source = "ncbi_doi"
                    stats['ncbi_doi'] += 1
            except Exception as e:
                print(f"  ⚠️  NCBI DOI 搜索出错: {e}")

        # 1b. DOI 查不到，用标题搜索
        if not pmid and title:
            try:
                pmid = search_pubmed_by_title(title, api_key)
                if pmid:
                    source = "ncbi_title"
                    stats['ncbi_title'] += 1
            except Exception as e:
                print(f"  ⚠️  NCBI 标题搜索出错: {e}")

        # 1c. 获取 NCBI 元数据
        if pmid:
            try:
                metadata = fetch_pubmed_metadata(pmid, api_key)
            except Exception as e:
                stats['errors'] += 1
                print(f"  ❌ [{idx}/{total}] NCBI 获取失败: {title[:40]}... -> {e}")
                metadata = {}

        time.sleep(ncbi_delay)

        # ── 第二引擎：Crossref（NCBI 没找到 abstract 时才用）──
        if not metadata.get('abstract'):
            crossref_meta = {}

            # 2a. 优先用 DOI 直接查询
            if doi:
                try:
                    crossref_meta = fetch_crossref_metadata(doi)
                    if crossref_meta.get('abstract'):
                        source = "crossref_doi"
                        stats['crossref_doi'] += 1
                    time.sleep(0.02)
                except Exception as e:
                    print(f"  ⚠️  Crossref DOI 查询出错: {e}")

            # 2b. DOI 没拿到 abstract，用标题搜索 Crossref
            if not crossref_meta.get('abstract') and title:
                try:
                    crossref_title_meta = search_crossref_by_title(title)
                    if crossref_title_meta.get('abstract'):
                        crossref_meta = crossref_title_meta
                        source = "crossref_title"
                        stats['crossref_title'] += 1
                    time.sleep(0.02)
                except Exception as e:
                    print(f"  ⚠️  Crossref 标题搜索出错: {e}")

            # 如果 Crossref 拿到了 abstract，用 Crossref 的数据
            if crossref_meta.get('abstract'):
                metadata = crossref_meta
            elif metadata:
                # NCBI 找到了但没有 abstract，Crossref 也没有 abstract
                # 保留 NCBI 的其他元数据（authors、journal 等）
                pass

        # 两个引擎都没找到
        if not metadata or not metadata.get('title'):
            stats['not_found'] += 1
            if idx % 10 == 0 or idx == total:
                print(f"  [{idx}/{total}] 未找到: {title[:50]}...")
            continue

        # ── 更新数据库 ──
        update_fields = []
        update_values = []

        if metadata.get('abstract') and len(metadata['abstract']) > 20:
            update_fields.append("abstract = ?")
            update_values.append(metadata['abstract'][:5000])
            stats['abstract_filled'] += 1

        # affiliations 只在数据库中没有时才更新
        if metadata.get('affiliations'):
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

        source_label = {
            'ncbi_doi': 'NCBI(DOI)',
            'ncbi_title': 'NCBI(标题)',
            'crossref_doi': 'Crossref(DOI)',
            'crossref_title': 'Crossref(标题)',
        }.get(source, source)

        if idx % 5 == 0 or idx == total or source in ('crossref_doi', 'crossref_title'):
            print(f"  [{idx}/{total}] ✓ ({source_label}) {title[:50]}...")

    conn.close()

    # 最终统计
    print()
    print("=" * 60)
    print("📊 双引擎抓取结果统计")
    print("=" * 60)
    print(f"  总论文数:              {total}")
    print(f"  跳过（已有abstract）:   {stats['skipped']}")
    print(f"  ─────────────────────────────────────")
    print(f"  NCBI DOI 搜索命中:     {stats['ncbi_doi']}")
    print(f"  NCBI 标题搜索命中:     {stats['ncbi_title']}")
    print(f"  Crossref DOI 命中:     {stats['crossref_doi']}")
    print(f"  Crossref 标题命中:     {stats['crossref_title']}")
    print(f"  所有引擎都未找到:      {stats['not_found']}")
    print(f"  错误:                  {stats['errors']}")
    print(f"  ─────────────────────────────────────")
    print(f"  填充 abstract:         {stats['abstract_filled']} 篇")
    print(f"  填充 affiliations:     {stats['affiliations_filled']} 篇")

    # 验证最终 abstract 填充率
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM papers WHERE abstract IS NOT NULL AND abstract != ''")
    has_abstract = cursor.fetchone()[0]
    print(f"\n✅ 最终有 abstract 的论文: {has_abstract}/{total}")
    conn.close()

    print("\n✅ 双引擎批量抓取完成！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 NCBI PubMed + Crossref 批量抓取论文元数据")
    parser.add_argument("db_path", nargs="?", default="data/research.db", help="数据库路径")
    parser.add_argument("--api-key", default="", help="NCBI API Key（可选，提高 NCBI 速率）")
    args = parser.parse_args()

    print("=" * 60)
    print("V25.18 NCBI PubMed + Crossref 双引擎元数据抓取")
    print("=" * 60)
    print()

    fetch_metadata(args.db_path, args.api_key)
