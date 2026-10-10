#!/usr/bin/env python3
"""
Sci-Pal 实验方法（Protocol）专项批量下载脚本 V1.0

专门下载生物医学实验方法类论文，支持多个 Protocol 专刊和来源：
  - Bio-protocol（斯坦福创立，OA，PMC收录）
  - STAR Protocols（Cell Press，OA，PMC收录）
  - Nature Protocols（部分OA）
  - Methods in Molecular Biology（Humana Press，部分OA）
  - Cold Spring Harbor Protocols（部分OA）
  - 通用 publication_type: Protocol 筛选

下载内容：
  - 摘要 JSON（abstracts_protocols/）
  - PMC 全文 XML（documents_protocols/，自动过滤只有摘要的）

使用方法：
  # 按主题搜索下载所有类型的protocol（默认100篇）
  python download_protocols.py --query "single cell RNA sequencing"

  # 只下载 Bio-protocol 期刊的
  python download_protocols.py --query "flow cytometry" --journal bio-protocol

  # 指定多个期刊
  python download_protocols.py --query "CRISPR" --journal bio-protocol,star-protocols

  # 每个主题下载200篇
  python download_protocols.py --query "western blot" --max 200

  # 批量主题下载（从内置主题列表）
  python download_protocols.py --batch

  # 只搜索不下载（预览）
  python download_protocols.py --query "ChIP-seq" --dry-run

  # 不过滤只有摘要的文章
  python download_protocols.py --query "PCR" --no-filter
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

# Windows 控制台编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# Protocol 期刊/来源配置
# ============================================================
PROTOCOL_JOURNALS = {
    "bio-protocol": {
        "name": "Bio-protocol",
        "publisher": "Stanford / Bio-protocol",
        "pmc_journal_title": "Bio Protoc",
        "description": "同行评审开放获取protocol期刊，5500+方案，89%可复现率",
        "oa": True,
    },
    "star-protocols": {
        "name": "STAR Protocols",
        "publisher": "Cell Press",
        "pmc_journal_title": "STAR Protoc",
        "description": "Cell Press旗下，结构化实验方案，OA",
        "oa": True,
    },
    "nature-protocols": {
        "name": "Nature Protocols",
        "publisher": "Springer Nature",
        "pmc_journal_title": "Nat Protoc",
        "description": "Nature系列，recipe风格分步protocol，部分OA",
        "oa": False,
    },
    "methods-mol-biol": {
        "name": "Methods in Molecular Biology",
        "publisher": "Humana Press / Springer",
        "pmc_journal_title": "Methods Mol Biol",
        "description": "经典实验室指南系列，部分OA章节",
        "oa": False,
    },
    "csh-protocols": {
        "name": "Cold Spring Harbor Protocols",
        "publisher": "Cold Spring Harbor Laboratory",
        "pmc_journal_title": "Cold Spring Harb Protoc",
        "description": "冷泉港实验室，28000+实验室指南，部分OA",
        "oa": False,
    },
    "jove": {
        "name": "Journal of Visualized Experiments (JoVE)",
        "publisher": "JoVE",
        "pmc_journal_title": "J Vis Exp",
        "description": "视频实验期刊，部分OA",
        "oa": False,
    },
}

# 内置批量主题列表（按研究领域分类）
BATCH_TOPICS = {
    "分子生物学": [
        "PCR amplification",
        "DNA extraction purification",
        "RNA extraction isolation",
        "western blot immunoblotting",
        "immunoprecipitation IP",
        "ChIP-seq chromatin immunoprecipitation",
        "cloning restriction enzyme",
        "plasmid transfection",
        "gel electrophoresis",
        "qPCR real-time PCR",
    ],
    "细胞生物学": [
        "cell culture maintenance",
        "cell transfection lipofectamine",
        "flow cytometry FACS",
        "immunofluorescence staining",
        "cell proliferation assay MTT",
        "apoptosis assay annexin",
        "cell cycle analysis",
        "confocal microscopy imaging",
        "co-culture cell",
        "cell sorting",
    ],
    "基因组学": [
        "single cell RNA sequencing scRNA-seq",
        "bulk RNA sequencing library prep",
        "whole exome sequencing WES",
        "ATAC-seq assay",
        "spatial transcriptomics",
        "CRISPR Cas9 gene editing",
        "DNA methylation bisulfite sequencing",
        "ChIP-seq histone modification",
        "scATAC-seq",
        "multi-omics integration",
    ],
    "蛋白质组学": [
        "mass spectrometry sample prep",
        "LC-MS/MS proteomics",
        "protein purification chromatography",
        "co-immunoprecipitation mass spec",
        "phosphoproteomics enrichment",
        "TMT labeling quantification",
        "label-free quantification LFQ",
        "glycoproteomics",
        "ubiquitination proteomics",
        "protein-protein interaction",
    ],
    "免疫学": [
        "ELISA enzyme-linked immunosorbent",
        "ELISpot assay",
        "T cell activation assay",
        "cytokine secretion assay",
        "immune cell isolation mouse spleen",
        "dendritic cell culture",
        "macrophage polarization",
        "neutralizing antibody assay",
        "complement assay",
        "adoptive cell transfer mouse",
    ],
    "生物信息学": [
        "RNA-seq data analysis pipeline",
        "single cell analysis Seurat",
        "genome assembly workflow",
        "variant calling GATK",
        "differential expression DESeq2",
        "pathway enrichment analysis",
        "protein structure prediction AlphaFold",
        "molecular docking",
        "metagenomics analysis pipeline",
        "machine learning bioinformatics",
    ],
    "肿瘤研究": [
        "tumor xenograft mouse model",
        "cell invasion migration assay transwell",
        "colony formation assay",
        "tumor spheroid culture",
        "angiogenesis assay",
        "drug sensitivity IC50 assay",
        "tumor microenvironment analysis",
        "cancer stem cell isolation",
        "PDX patient-derived xenograft",
        "tumor immunotherapy mouse",
    ],
    "神经科学": [
        "primary neuron culture",
        "brain slice preparation",
        "patch clamp electrophysiology",
        "immunohistochemistry brain",
        "behavioral test mouse",
        "neural stem cell differentiation",
        "synapse staining",
        "calcium imaging neuron",
        "microglia isolation culture",
        "astrocyte culture",
    ],
}

# ============================================================
# NCBI E-utilities 配置
# ============================================================
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json,application/xml,*/*",
}

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

DEFAULT_TOOL = "scipal-protocol-downloader"
DEFAULT_EMAIL = "chenwei-ucas@outlook.com"
DEFAULT_API_KEY = "76012a329673a2911604807c76294bf98507"

RATE_LIMIT_NO_KEY = 0.35
RATE_LIMIT_WITH_KEY = 0.12

MAX_RETRIES = 3
RETRY_DELAY = 5


class ProtocolDownloader:
    """实验方法（Protocol）专项批量下载器"""

    def __init__(
        self,
        tool: str = DEFAULT_TOOL,
        email: str = DEFAULT_EMAIL,
        api_key: str = None,
        abstract_dir: str = "abstracts_protocols",
        xml_dir: str = "documents_protocols",
        verbose: bool = True,
    ):
        self.tool = tool
        self.email = email
        self.api_key = api_key
        self.abstract_dir = Path(abstract_dir)
        self.xml_dir = Path(xml_dir)
        self.verbose = verbose

        self.rate_limit = RATE_LIMIT_WITH_KEY if api_key else RATE_LIMIT_NO_KEY
        self.last_request_time = 0

        self.stats = {
            "searched": 0,
            "abstracts_downloaded": 0,
            "xml_downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "filtered_no_fulltext": 0,
            "failed_ids": [],
        }
        self.filter_no_fulltext = True

        self.abstract_dir.mkdir(parents=True, exist_ok=True)
        self.xml_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit_wait(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _build_params(self, **kwargs) -> dict:
        params = {"tool": self.tool, "email": self.email}
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(kwargs)
        return params

    def _request(self, url: str, params: dict = None, timeout: int = 120):
        """带重试的HTTP请求"""
        for attempt in range(MAX_RETRIES):
            try:
                self._rate_limit_wait()
                resp = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY * (attempt + 1)
                    if self.verbose:
                        print(f"  ⚠️  请求失败(尝试 {attempt+1}/{MAX_RETRIES}): {e}，{wait}秒后重试...")
                    time.sleep(wait)
                else:
                    raise

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    # ============================================================
    # 搜索：PubMed ESearch
    # ============================================================
    def search_pubmed(self, query: str, max_results: int = 100, journal: str = None) -> list:
        """
        在PubMed中搜索protocol相关文章
        支持按特定期刊筛选，或通用 publication_type 筛选
        """
        # 构建搜索查询
        if journal and journal in PROTOCOL_JOURNALS:
            journal_info = PROTOCOL_JOURNALS[journal]
            # 特定期刊 + 主题关键词
            search_query = f'({query}) AND "{journal_info["pmc_journal_title"]}"[Journal]'
            self._log(f"  📖 期刊筛选: {journal_info['name']} ({journal_info['pmc_journal_title']})")
        else:
            # 通用：主题 + protocol/methods关键词（PubMed没有protocol[Publication Type]）
            search_query = f'({query}) AND ("protocols"[Title/Abstract] OR "method"[Title/Abstract] OR "methods"[Journal] OR "protocol"[Title/Abstract])'

        # 加免费全文过滤（优先OA，用 free full text 而不是 open access）
        search_query += ' AND free full text[Filter]'

        self._log(f"  🔍 搜索查询: {search_query[:100]}...")

        all_ids = []
        retstart = 0
        retmax = min(100, max_results)

        while len(all_ids) < max_results:
            params = self._build_params(
                db="pubmed",
                term=search_query,
                retstart=retstart,
                retmax=retmax,
                retmode="json",
                sort="relevance",
            )
            resp = self._request(f"{EUTILS_BASE}/esearch.fcgi", params=params)
            data = resp.json()

            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                break

            all_ids.extend(id_list)
            retstart += retmax

            if len(id_list) < retmax:
                break

        all_ids = all_ids[:max_results]
        self.stats["searched"] += len(all_ids)
        self._log(f"  ✅ 找到 {len(all_ids)} 个 PMID")
        return all_ids

    # ============================================================
    # 摘要下载：PubMed ESummary + EFetch
    # ============================================================
    def fetch_abstracts(self, pmids: list, output_file: str = None) -> list:
        """批量下载摘要，保存为JSON"""
        if not pmids:
            return []

        self._log(f"  📥 下载 {len(pmids)} 篇摘要...")

        all_abstracts = []
        batch_size = 100

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            id_str = ",".join(batch)

            params = self._build_params(
                db="pubmed",
                id=id_str,
                retmode="xml",
            )
            resp = self._request(f"{EUTILS_BASE}/efetch.fcgi", params=params)

            # 解析XML
            root = ET.fromstring(resp.content)
            for article in root.findall(".//PubmedArticle"):
                abstract_data = self._parse_pubmed_article(article)
                if abstract_data:
                    all_abstracts.append(abstract_data)

            self._log(f"    解析 {i + len(batch)}/{len(pmids)}...")

        # 保存
        if output_file is None:
            output_file = self.abstract_dir / f"protocols_{int(time.time())}.json"
        else:
            output_file = Path(output_file)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_abstracts, f, ensure_ascii=False, indent=2)

        self.stats["abstracts_downloaded"] += len(all_abstracts)
        self._log(f"  ✅ 共解析 {len(all_abstracts)} 篇摘要，保存到: {output_file}")
        return all_abstracts

    def _parse_pubmed_article(self, article) -> dict:
        """解析单篇PubMed文章为摘要数据"""
        try:
            medline = article.find(".//MedlineCitation")
            if medline is None:
                return None

            pmid_elem = medline.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""

            article_elem = medline.find(".//Article")
            if article_elem is None:
                return None

            # 标题
            title_elem = article_elem.find(".//ArticleTitle")
            title = "".join(title_elem.itertext()) if title_elem is not None else ""

            # 期刊
            journal_elem = article_elem.find(".//Journal")
            journal_title = ""
            journal_iso = ""
            if journal_elem is not None:
                jt = journal_elem.find(".//Title")
                journal_title = jt.text if jt is not None else ""
                ji = journal_elem.find(".//ISOAbbreviation")
                journal_iso = ji.text if ji is not None else ""

            # 摘要文本
            abstract_text_parts = []
            abstract_elem = article_elem.find(".//Abstract")
            if abstract_elem is not None:
                for abs_text in abstract_elem.findall(".//AbstractText"):
                    label = abs_text.get("Label", "")
                    text = "".join(abs_text.itertext()).strip()
                    if label:
                        abstract_text_parts.append(f"{label}: {text}")
                    else:
                        abstract_text_parts.append(text)
            abstract_text = " ".join(abstract_text_parts)

            # 作者
            authors = []
            author_list = article_elem.find(".//AuthorList")
            if author_list is not None:
                for author in author_list.findall(".//Author"):
                    last = author.find(".//LastName")
                    first = author.find(".//ForeName")
                    if last is not None and first is not None:
                        authors.append(f"{last.text} {first.text}")
                    elif last is not None:
                        authors.append(last.text)

            # 发表日期
            pub_date = ""
            pub_date_elem = article_elem.find(".//PubDate")
            if pub_date_elem is not None:
                year = pub_date_elem.find(".//Year")
                month = pub_date_elem.find(".//Month")
                day = pub_date_elem.find(".//Day")
                parts = []
                if year is not None:
                    parts.append(year.text)
                if month is not None:
                    parts.append(month.text)
                if day is not None:
                    parts.append(day.text)
                pub_date = "-".join(parts)

            # DOI
            doi = ""
            for eid in article.findall(".//ArticleId"):
                if eid.get("IdType") == "doi":
                    doi = eid.text or ""
                    break

            # 发表类型
            pub_types = []
            for pt in article.findall(".//PublicationType"):
                if pt.text:
                    pub_types.append(pt.text)

            # PMC ID（如果有）
            pmcid = ""
            for eid in article.findall(".//ArticleId"):
                if eid.get("IdType") == "pmc":
                    pmcid = eid.text or ""
                    break

            return {
                "pmid": pmid,
                "pmcid": pmcid,
                "doi": doi,
                "title": title,
                "authors": authors,
                "journal": journal_title,
                "journal_iso": journal_iso,
                "pub_date": pub_date,
                "abstract": abstract_text,
                "publication_types": pub_types,
                "source": "protocol_downloader",
            }
        except Exception as e:
            self._log(f"  ⚠️  解析文章失败: {e}")
            return None

    # ============================================================
    # PMC全文XML下载
    # ============================================================
    def fetch_pmc_xml(self, abstracts: list, max_download: int = None):
        """从摘要列表中提取有PMC ID的，下载全文XML"""
        pmc_articles = [a for a in abstracts if a.get("pmcid")]
        if not pmc_articles:
            self._log("  ⚠️  没有找到有PMC ID的文章，跳过XML下载")
            return

        if max_download:
            pmc_articles = pmc_articles[:max_download]

        self._log(f"  📄 下载 {len(pmc_articles)} 篇PMC全文XML...")

        for i, article in enumerate(pmc_articles, 1):
            pmcid = article["pmcid"]
            pmid = article["pmid"]
            title = article["title"][:60]

            # 输出文件名
            safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title[:40])
            output_file = self.xml_dir / f"paper_{pmcid}_{safe_title}.xml"

            # 已下载则跳过
            if output_file.exists():
                self.stats["skipped"] += 1
                self._log(f"  [{i}/{len(pmc_articles)}] ⏭️  已存在，跳过: {pmcid}")
                continue

            try:
                # 使用EFetch获取PMC XML
                params = self._build_params(
                    db="pmc",
                    id=pmcid,
                    retmode="xml",
                )
                resp = self._request(f"{EUTILS_BASE}/efetch.fcgi", params=params)

                # 检查是否有全文（<body>标签）
                if self.filter_no_fulltext:
                    has_body = self._check_xml_has_body(resp.content)
                    if not has_body:
                        self.stats["filtered_no_fulltext"] += 1
                        self._log(f"  [{i}/{len(pmc_articles)}] 🚫 只有摘要，过滤: {pmcid}")
                        continue

                # 保存
                with open(output_file, "wb") as f:
                    f.write(resp.content)

                self.stats["xml_downloaded"] += 1
                self._log(f"  [{i}/{len(pmc_articles)}] ✅ 下载: {pmcid} - {title[:40]}...")

            except Exception as e:
                self.stats["failed"] += 1
                self.stats["failed_ids"].append(pmcid)
                self._log(f"  [{i}/{len(pmc_articles)}] ❌ 失败: {pmcid} - {e}")

    def _check_xml_has_body(self, xml_content: bytes) -> bool:
        """检查XML是否有<body>标签（有全文的标志）"""
        try:
            root = ET.fromstring(xml_content)
            # JATS XML 中 <body> 是全文正文
            body = root.find(".//body")
            return body is not None and len(list(body)) > 0
        except Exception:
            return False

    # ============================================================
    # 主流程：按主题下载
    # ============================================================
    def download_by_topic(
        self,
        query: str,
        max_results: int = 100,
        journal: str = None,
        download_xml: bool = True,
        dry_run: bool = False,
    ):
        """按主题下载protocol文章"""
        self._log("=" * 70)
        self._log(f"📥 下载主题: {query}")
        if journal:
            self._log(f"📖 特定期刊: {journal}")
        self._log(f"📊 最大数量: {max_results}")
        self._log("=" * 70)

        # 1. 搜索
        pmids = self.search_pubmed(query, max_results, journal)

        if dry_run:
            self._log(f"  🔍 dry-run模式，找到 {len(pmids)} 篇，不下载")
            return pmids

        if not pmids:
            self._log("  ⚠️  没有找到结果")
            return []

        # 2. 下载摘要
        safe_query = "".join(c if c.isalnum() or c in "-_" else "_" for c in query[:50])
        abstract_file = self.abstract_dir / f"{safe_query}.json"
        abstracts = self.fetch_abstracts(pmids, output_file=str(abstract_file))

        # 3. 下载PMC全文XML
        if download_xml and abstracts:
            self.fetch_pmc_xml(abstracts)

        return abstracts

    def download_batch(self, categories: list = None, max_per_topic: int = 50):
        """批量下载内置主题"""
        self._log("=" * 70)
        self._log("🚀 批量下载 Protocol 主题")
        self._log("=" * 70)

        total_topics = 0
        if categories:
            for cat in categories:
                if cat in BATCH_TOPICS:
                    total_topics += len(BATCH_TOPICS[cat])
        else:
            for cat in BATCH_TOPICS:
                total_topics += len(BATCH_TOPICS[cat])

        self._log(f"  📋 共 {total_topics} 个主题，每个最多 {max_per_topic} 篇")
        self._log(f"  ⏳ 预计最多 {total_topics * max_per_topic} 篇（过滤后会更少）")
        self._log("")

        topic_count = 0
        for category, topics in BATCH_TOPICS.items():
            if categories and category not in categories:
                continue

            self._log(f"\n{'#'*70}")
            self._log(f"# 分类: {category} ({len(topics)}个主题)")
            self._log(f"{'#'*70}")

            for topic in topics:
                topic_count += 1
                self._log(f"\n--- 进度: [{topic_count}/{total_topics}] {topic} ---")
                try:
                    self.download_by_topic(topic, max_per_topic)
                except Exception as e:
                    self._log(f"  ❌ 主题下载失败: {e}")
                    continue

        self._log("\n" + "=" * 70)
        self._log("✅ 批量下载完成")
        self.print_stats()

    def print_stats(self):
        """打印统计信息"""
        self._log("\n" + "=" * 50)
        self._log("📊 下载统计")
        self._log("=" * 50)
        self._log(f"  搜索到: {self.stats['searched']} 篇")
        self._log(f"  摘要下载: {self.stats['abstracts_downloaded']} 篇")
        self._log(f"  XML下载: {self.stats['xml_downloaded']} 篇")
        self._log(f"  跳过(已存在): {self.stats['skipped']} 篇")
        self._log(f"  过滤(只有摘要): {self.stats['filtered_no_fulltext']} 篇")
        self._log(f"  失败: {self.stats['failed']} 篇")
        if self.stats["failed_ids"]:
            self._log(f"  失败ID: {', '.join(self.stats['failed_ids'][:10])}")
        self._log("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Sci-Pal 实验方法（Protocol）专项批量下载器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
支持的期刊 (--journal):
  bio-protocol    - Bio-protocol (OA, PMC收录)
  star-protocols  - STAR Protocols (OA, Cell Press)
  nature-protocols - Nature Protocols (部分OA)
  methods-mol-biol - Methods in Molecular Biology (部分OA)
  csh-protocols   - Cold Spring Harbor Protocols (部分OA)
  jove            - Journal of Visualized Experiments (部分OA)

批量分类 (--batch-cat):
  分子生物学, 细胞生物学, 基因组学, 蛋白质组学,
  免疫学, 生物信息学, 肿瘤研究, 神经科学
        """,
    )
    parser.add_argument("--query", "-q", type=str, help="搜索关键词（主题）")
    parser.add_argument("--journal", "-j", type=str, default=None,
                        help="特定期刊筛选（不指定则搜索所有protocol类型）")
    parser.add_argument("--max", "-m", type=int, default=100, help="每个主题最大下载数量（默认100）")
    parser.add_argument("--batch", action="store_true", help="批量下载内置主题列表")
    parser.add_argument("--batch-cat", type=str, default=None,
                        help="批量下载指定分类（逗号分隔，如 '分子生物学,基因组学'）")
    parser.add_argument("--abstract-dir", type=str, default="abstracts_protocols", help="摘要输出目录")
    parser.add_argument("--xml-dir", type=str, default="documents_protocols", help="XML输出目录")
    parser.add_argument("--no-filter", action="store_true", help="不过滤只有摘要的文章")
    parser.add_argument("--no-xml", action="store_true", help="只下载摘要，不下载PMC全文XML")
    parser.add_argument("--dry-run", action="store_true", help="只搜索不下载")
    parser.add_argument("--api-key", type=str, default=DEFAULT_API_KEY, help="NCBI API Key")
    parser.add_argument("--email", type=str, default=DEFAULT_EMAIL, help="联系邮箱")

    args = parser.parse_args()

    # 校验
    if not args.query and not args.batch and not args.batch_cat:
        parser.error("请指定 --query 或 --batch 或 --batch-cat")

    # 创建下载器
    downloader = ProtocolDownloader(
        api_key=args.api_key,
        email=args.email,
        abstract_dir=args.abstract_dir,
        xml_dir=args.xml_dir,
    )

    if args.no_filter:
        downloader.filter_no_fulltext = False
        print("⚠️  已关闭只有摘要过滤")

    try:
        if args.batch or args.batch_cat:
            # 批量下载
            categories = None
            if args.batch_cat:
                categories = [c.strip() for c in args.batch_cat.split(",")]
            downloader.download_batch(categories=categories, max_per_topic=args.max)
        else:
            # 单主题下载
            downloader.download_by_topic(
                query=args.query,
                max_results=args.max,
                journal=args.journal,
                download_xml=not args.no_xml,
                dry_run=args.dry_run,
            )
            downloader.print_stats()

    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断，已下载的会保留")
        downloader.print_stats()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
