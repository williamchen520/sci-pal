"""
Online Search: 在线搜索 NCBI PubMed + PMC
V1.0 - 混合检索系统 P0 模块

同时搜索 PubMed（摘要）和 PMC（开放获取全文），返回统一格式结果。
内置 NCBI API 限速、缓存、错误重试。

跟本地搜索结果格式统一，方便 hybrid_retriever 合并去重。
"""

import time
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests


# ============================================================
# NCBI E-utilities 配置
# ============================================================
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 工具标识（NCBI 要求每个请求带 tool 和 email）
DEFAULT_TOOL = "scipal-online-search"
DEFAULT_EMAIL = "chenwei-ucas@outlook.com"
DEFAULT_API_KEY = "76012a329673a2911604807c76294bf98507"

# 速率限制（秒/请求）
RATE_LIMIT_NO_KEY = 0.35   # 3次/秒
RATE_LIMIT_WITH_KEY = 0.12  # 10次/秒

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5

# 缓存目录
CACHE_DIR = Path("data/online_search_cache")


class OnlineSearchResult:
    """
    统一格式的在线搜索结果，跟本地论文格式兼容。
    """
    def __init__(
        self,
        paper_id: str,
        title: str,
        authors: str = "",
        abstract: str = "",
        journal: str = "",
        year: Optional[int] = None,
        doi: str = "",
        pmid: str = "",
        pmcid: str = "",
        source: str = "online",
        has_fulltext: bool = False,
        in_local_db: bool = False,
        relevance_score: float = 0.0,
        raw_data: Optional[Dict] = None,
    ):
        self.paper_id = paper_id          # 统一用 PMCID（如果有）或 PMID
        self.title = title
        self.authors = authors
        self.abstract = abstract
        self.journal = journal
        self.year = year
        self.doi = doi
        self.pmid = pmid
        self.pmcid = pmcid
        self.source = source               # "online_pubmed" / "online_pmc" / "local"
        self.has_fulltext = has_fulltext   # PMC 是否有开放获取全文
        self.in_local_db = in_local_db     # 是否已在本地数据库
        self.relevance_score = relevance_score  # 相关性分数（0-1）
        self.raw_data = raw_data or {}     # 原始 NCBI 返回数据

    def to_dict(self) -> Dict:
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "journal": self.journal,
            "year": self.year,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "source": self.source,
            "has_fulltext": self.has_fulltext,
            "in_local_db": self.in_local_db,
            "relevance_score": round(self.relevance_score, 4),
        }


class OnlineSearcher:
    """
    在线搜索 NCBI PubMed + PMC。

    使用方法：
        searcher = OnlineSearcher()
        results = searcher.search("STAT1 interferon", max_results=50)
        for r in results:
            print(r.title, r.pmcid, r.has_fulltext)
    """

    def __init__(
        self,
        api_key: str = DEFAULT_API_KEY,
        tool: str = DEFAULT_TOOL,
        email: str = DEFAULT_EMAIL,
        cache_enabled: bool = True,
        verbose: bool = True,
    ):
        self.api_key = api_key
        self.tool = tool
        self.email = email
        self.cache_enabled = cache_enabled
        self.verbose = verbose

        self.rate_limit = RATE_LIMIT_WITH_KEY if api_key else RATE_LIMIT_NO_KEY
        self.last_request_time = 0

        # 缓存目录
        if cache_enabled:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _build_params(self, **kwargs) -> Dict:
        """构建 NCBI API 请求参数，自动加 tool/email/api_key。"""
        params = {
            "tool": self.tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(kwargs)
        return params

    def _rate_limit_wait(self):
        """限速等待，确保不超过 NCBI API 频率限制。"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _request(self, url: str, params: Dict, timeout: int = 60) -> Optional[requests.Response]:
        """带重试和限速的 HTTP 请求。"""
        for attempt in range(MAX_RETRIES):
            self._rate_limit_wait()
            try:
                resp = requests.get(url, params=params, timeout=timeout)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    # 限速，等久一点
                    wait_time = RETRY_DELAY * (attempt + 1)
                    if self.verbose:
                        print(f"  ⚠️  NCBI 限速，等待 {wait_time} 秒后重试 ({attempt+1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                else:
                    if self.verbose:
                        print(f"  ⚠️  HTTP {resp.status_code}，重试 ({attempt+1}/{MAX_RETRIES})")
                    time.sleep(RETRY_DELAY)
            except requests.RequestException as e:
                if self.verbose:
                    print(f"  ⚠️  请求异常: {e}，重试 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(RETRY_DELAY)
        return None

    def _cache_key(self, db: str, query: str, max_results: int) -> str:
        """生成缓存键。"""
        raw = f"{db}:{query}:{max_results}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_get(self, cache_key: str) -> Optional[List[Dict]]:
        """从缓存读取。"""
        if not self.cache_enabled:
            return None
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _cache_set(self, cache_key: str, data: List[Dict]):
        """写入缓存。"""
        if not self.cache_enabled:
            return
        cache_file = CACHE_DIR / f"{cache_key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _esearch(self, db: str, query: str, max_results: int = 50) -> List[str]:
        """
        ESearch: 搜索 NCBI 数据库，返回 ID 列表。

        Args:
            db: "pubmed" 或 "pmc"
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            ID 列表（PMID 或 PMCID 的数字部分）
        """
        # PMC 搜索时加开放获取过滤
        search_term = query
        if db == "pmc":
            search_term = f"{query} AND open access[filter]"

        params = self._build_params(
            db=db,
            term=search_term,
            retmax=max_results,
            retmode="json",
            sort="relevance",
        )

        resp = self._request(f"{EUTILS_BASE}/esearch.fcgi", params)
        if not resp:
            return []

        try:
            data = resp.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            return id_list
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  ESearch 解析失败: {e}")
            return []

    def _esummary(self, db: str, id_list: List[str]) -> List[Dict]:
        """
        ESummary: 批量获取论文元数据。

        Args:
            db: "pubmed" 或 "pmc"
            id_list: ID 列表

        Returns:
            元数据字典列表
        """
        if not id_list:
            return []

        # 批量处理，每次最多 200 个 ID
        results = []
        batch_size = 200

        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            params = self._build_params(
                db=db,
                id=",".join(batch),
                retmode="json",
            )

            resp = self._request(f"{EUTILS_BASE}/esummary.fcgi", params)
            if not resp:
                continue

            try:
                data = resp.json()
                result = data.get("result", {})
                for uid in result.get("uids", []):
                    if uid in result:
                        results.append(result[uid])
            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️  ESummary 解析失败: {e}")

        return results

    def _parse_pubmed_summary(self, summary: Dict) -> OnlineSearchResult:
        """解析 PubMed ESummary 返回的单条记录。"""
        uid = summary.get("uid", "")
        pmid = uid

        # 标题
        title = summary.get("title", "").strip()
        # 去掉末尾的句号
        if title.endswith("."):
            title = title[:-1]

        # 作者
        authors_list = summary.get("authors", [])
        authors = ", ".join(
            a.get("name", "") for a in authors_list if a.get("name")
        )

        # 期刊
        journal = summary.get("fulljournalname", "") or summary.get("source", "")

        # 年份
        pubdate = summary.get("pubdate", "")
        year = None
        if pubdate and len(pubdate) >= 4:
            try:
                year = int(pubdate[:4])
            except ValueError:
                pass

        # DOI
        article_ids = summary.get("articleids", [])
        doi = ""
        pmcid = ""
        for aid in article_ids:
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
            elif aid.get("idtype") == "pmc":
                pmcid = aid.get("value", "")

        # 摘要（ESummary 里没有摘要，需要单独 EFetch，这里先留空）
        abstract = ""

        # paper_id 优先用 PMCID，没有用 PMID
        paper_id = pmcid if pmcid else f"PMID{pmid}"

        return OnlineSearchResult(
            paper_id=paper_id,
            title=title,
            authors=authors,
            abstract=abstract,
            journal=journal,
            year=year,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            source="online_pubmed",
            has_fulltext=bool(pmcid),  # 有 PMCID 说明可能有 PMC 全文
            raw_data=summary,
        )

    def _parse_pmc_summary(self, summary: Dict) -> OnlineSearchResult:
        """解析 PMC ESummary 返回的单条记录。"""
        uid = summary.get("uid", "")
        pmcid = f"PMC{uid}"

        # 标题
        title = summary.get("title", "").strip()
        if title.endswith("."):
            title = title[:-1]

        # 作者
        authors_list = summary.get("authors", [])
        authors = ", ".join(
            a.get("name", "") for a in authors_list if a.get("name")
        )

        # 期刊
        journal = summary.get("fulljournalname", "") or summary.get("source", "")

        # 年份
        pubdate = summary.get("pubdate", "")
        year = None
        if pubdate and len(pubdate) >= 4:
            try:
                year = int(pubdate[:4])
            except ValueError:
                pass

        # DOI 和 PMID
        article_ids = summary.get("articleids", [])
        doi = ""
        pmid = ""
        for aid in article_ids:
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
            elif aid.get("idtype") == "pubmed":
                pmid = aid.get("value", "")

        # PMC 搜索结果默认有开放获取全文
        has_fulltext = True

        return OnlineSearchResult(
            paper_id=pmcid,
            title=title,
            authors=authors,
            abstract="",  # ESummary 没有摘要
            journal=journal,
            year=year,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            source="online_pmc",
            has_fulltext=has_fulltext,
            raw_data=summary,
        )

    def search_pubmed(self, query: str, max_results: int = 50) -> List[OnlineSearchResult]:
        """
        只搜索 PubMed。

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            OnlineSearchResult 列表
        """
        if self.verbose:
            print(f"  🌐 在线搜索 PubMed: {query}")

        # 缓存检查
        cache_key = self._cache_key("pubmed", query, max_results)
        cached = self._cache_get(cache_key)
        if cached is not None:
            if self.verbose:
                print(f"    ✅ 缓存命中: {len(cached)} 篇")
            return [OnlineSearchResult(**r) for r in cached]

        # 搜索
        id_list = self._esearch("pubmed", query, max_results)
        if not id_list:
            if self.verbose:
                print(f"    ⚠️  未找到结果")
            return []

        if self.verbose:
            print(f"    找到 {len(id_list)} 个 PMID，获取元数据...")

        # 批量获取元数据
        summaries = self._esummary("pubmed", id_list)

        # 解析
        results = []
        for summary in summaries:
            try:
                result = self._parse_pubmed_summary(summary)
                # 按搜索顺序设置相关性分数（越靠前分越高）
                result.relevance_score = max(0.0, 1.0 - len(results) / max(len(summaries), 1))
                results.append(result)
            except Exception as e:
                if self.verbose:
                    print(f"    ⚠️  解析失败: {e}")

        # 写入缓存
        self._cache_set(cache_key, [r.to_dict() for r in results])

        if self.verbose:
            print(f"    ✅ 返回 {len(results)} 篇 PubMed 结果")

        return results

    def search_pmc(self, query: str, max_results: int = 50) -> List[OnlineSearchResult]:
        """
        只搜索 PMC（开放获取全文）。

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            OnlineSearchResult 列表
        """
        if self.verbose:
            print(f"  🌐 在线搜索 PMC: {query}")

        # 缓存检查
        cache_key = self._cache_key("pmc", query, max_results)
        cached = self._cache_get(cache_key)
        if cached is not None:
            if self.verbose:
                print(f"    ✅ 缓存命中: {len(cached)} 篇")
            return [OnlineSearchResult(**r) for r in cached]

        # 搜索
        id_list = self._esearch("pmc", query, max_results)
        if not id_list:
            if self.verbose:
                print(f"    ⚠️  未找到结果")
            return []

        if self.verbose:
            print(f"    找到 {len(id_list)} 个 PMCID，获取元数据...")

        # 批量获取元数据
        summaries = self._esummary("pmc", id_list)

        # 解析
        results = []
        for summary in summaries:
            try:
                result = self._parse_pmc_summary(summary)
                result.relevance_score = max(0.0, 1.0 - len(results) / max(len(summaries), 1))
                results.append(result)
            except Exception as e:
                if self.verbose:
                    print(f"    ⚠️  解析失败: {e}")

        # 写入缓存
        self._cache_set(cache_key, [r.to_dict() for r in results])

        if self.verbose:
            print(f"    ✅ 返回 {len(results)} 篇 PMC 结果")

        return results

    def search(self, query: str, max_results: int = 50,
               search_pubmed: bool = True, search_pmc: bool = True) -> List[OnlineSearchResult]:
        """
        同时搜索 PubMed + PMC，合并结果（不去重，去重由 hybrid_retriever 做）。

        Args:
            query: 搜索关键词
            max_results: 每个数据库的最大结果数
            search_pubmed: 是否搜索 PubMed
            search_pmc: 是否搜索 PMC

        Returns:
            OnlineSearchResult 列表（PubMed + PMC 合并）
        """
        results = []

        if search_pubmed:
            pubmed_results = self.search_pubmed(query, max_results)
            results.extend(pubmed_results)

        if search_pmc:
            pmc_results = self.search_pmc(query, max_results)
            results.extend(pmc_results)

        if self.verbose:
            print(f"  🌐 在线搜索总计: {len(results)} 篇 (PubMed+PMC)")

        return results


# 单例
_online_searcher: Optional[OnlineSearcher] = None


def get_online_searcher() -> OnlineSearcher:
    """获取在线搜索器单例。"""
    global _online_searcher
    if _online_searcher is None:
        _online_searcher = OnlineSearcher()
    return _online_searcher
