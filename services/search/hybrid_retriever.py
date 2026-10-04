"""
Hybrid Retriever: 混合检索（本地 + 在线 NCBI/PMC）
V1.0 - 混合检索系统 P0 模块

同时搜索本地数据库和在线 NCBI PubMed/PMC，结果合并、三级去重、统一排序。

核心原则：检索层接口不变，只增加数据来源。
本地检索逻辑完全复用，在线检索作为额外数据源并行执行。

去重策略（三级）：
  1. PMCID（最精确，PMC 全文 ID）
  2. PMID（PubMed ID）
  3. DOI（数字对象标识符）
任一匹配即认为是同一篇论文，优先保留本地版本。
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from services.search.hybrid_search import HybridSearch
from services.search.online_search import OnlineSearcher, OnlineSearchResult


# 本地数据库路径（跟 api_server.py 保持一致）
DB_PATH = "data/research.db"


class HybridRetriever:
    """
    混合检索器：本地 + 在线同时搜索，合并去重。

    使用方法：
        retriever = HybridRetriever()
        results = retriever.search_papers(
            query="STAT1 interferon",
            top_k=20,
            use_online=True,
        )
        for r in results:
            print(f"[{r['source']}] {r['title']} (score={r['score']:.2f})")
    """

    def __init__(
        self,
        use_online: bool = True,
        online_max_results: int = 30,
        verbose: bool = True,
    ):
        self.use_online = use_online
        self.online_max_results = online_max_results
        self.verbose = verbose

        # 本地检索器（复用现有 HybridSearch）
        try:
            self.local_searcher = HybridSearch()
            if self.verbose:
                print("✅ 混合检索器：本地检索已加载")
        except Exception as e:
            if self.verbose:
                print(f"⚠️  混合检索器：本地检索加载失败: {e}")
            self.local_searcher = None

        # 在线检索器
        if use_online:
            try:
                self.online_searcher = OnlineSearcher(verbose=verbose)
                if self.verbose:
                    print("✅ 混合检索器：在线检索已加载")
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  混合检索器：在线检索加载失败: {e}")
                self.online_searcher = None
        else:
            self.online_searcher = None

        # 本地论文 ID 集合（用于快速判断是否在本地）
        self._local_paper_ids: Optional[set] = None
        self._local_paper_meta: Optional[Dict[str, Dict]] = None

    def _load_local_paper_index(self):
        """
        加载本地论文索引（PMID/PMCID/DOI → paper_id 映射），用于快速去重。
        只加载一次，后续复用。
        """
        if self._local_paper_ids is not None:
            return

        self._local_paper_ids = set()
        self._local_paper_meta = {}

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT paper_id, title, authors, journal, year, doi FROM papers"
            ).fetchall()
            conn.close()

            for row in rows:
                paper_id = row["paper_id"]
                self._local_paper_ids.add(paper_id)
                self._local_paper_meta[paper_id] = {
                    "paper_id": paper_id,
                    "title": row["title"] or "",
                    "authors": row["authors"] or "",
                    "journal": row["journal"] or "",
                    "year": row["year"],
                    "doi": row["doi"] or "",
                }

            if self.verbose:
                print(f"  📚 本地论文索引: {len(self._local_paper_ids)} 篇")

        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  加载本地论文索引失败: {e}")

    def _extract_identifiers(self, paper: Dict) -> Tuple[str, str, str]:
        """
        从论文字典中提取三级标识符：(pmcid, pmid, doi)。

        本地论文的 paper_id 可能是 PMCID 或 PMID 或其他格式，
        需要智能识别。
        """
        pmcid = ""
        pmid = ""
        doi = (paper.get("doi") or "").lower().strip()

        paper_id = (paper.get("paper_id") or "").strip()

        # 识别 PMCID（以 PMC 开头）
        if paper_id.upper().startswith("PMC"):
            pmcid = paper_id.upper()

        # 识别 PMID（以 PMID 开头，或者纯数字且长度 7-8 位）
        if paper_id.upper().startswith("PMID"):
            pmid = paper_id.upper().replace("PMID", "")
        elif paper_id.isdigit() and 7 <= len(paper_id) <= 8:
            pmid = paper_id

        # 从额外字段提取（在线搜索结果会有这些字段）
        if not pmcid and paper.get("pmcid"):
            pmcid = str(paper["pmcid"]).upper()
        if not pmid and paper.get("pmid"):
            pmid = str(paper["pmid"])

        return pmcid, pmid, doi

    def _is_duplicate(self, paper: Dict, seen_identifiers: Dict[str, set]) -> bool:
        """
        检查论文是否重复（三级标识符任一匹配即重复）。

        Args:
            paper: 论文字典
            seen_identifiers: 已见过的标识符集合 {"pmcid": set, "pmid": set, "doi": set}

        Returns:
            True 如果重复
        """
        pmcid, pmid, doi = self._extract_identifiers(paper)

        if pmcid and pmcid in seen_identifiers["pmcid"]:
            return True
        if pmid and pmid in seen_identifiers["pmid"]:
            return True
        if doi and doi in seen_identifiers["doi"]:
            return True

        # 不重复，加入已见集合
        if pmcid:
            seen_identifiers["pmcid"].add(pmcid)
        if pmid:
            seen_identifiers["pmid"].add(pmid)
        if doi:
            seen_identifiers["doi"].add(doi)

        return False

    def _normalize_local_paper(self, paper: Dict) -> Dict:
        """
        将本地论文格式标准化为统一格式。
        """
        return {
            "paper_id": paper.get("paper_id", ""),
            "title": paper.get("title", ""),
            "authors": paper.get("authors", ""),
            "abstract": paper.get("abstract", ""),
            "journal": paper.get("journal", ""),
            "year": paper.get("year"),
            "doi": paper.get("doi", ""),
            "pmid": paper.get("pmid", ""),
            "pmcid": paper.get("pmcid", ""),
            "source": "local",
            "has_fulltext": True,  # 本地论文默认有全文
            "in_local_db": True,
            "score": paper.get("score", paper.get("relevance_score", 0.0)),
        }

    def _normalize_online_result(self, result: OnlineSearchResult) -> Dict:
        """
        将在线搜索结果标准化为统一格式。
        """
        d = result.to_dict()
        d["score"] = d.pop("relevance_score", 0.0)
        d["in_local_db"] = self._check_in_local_db(d)
        return d

    def _check_in_local_db(self, paper: Dict) -> bool:
        """
        检查在线论文是否已在本地数据库（三级标识符匹配）。
        """
        self._load_local_paper_index()

        if not self._local_paper_meta:
            return False

        pmcid, pmid, doi = self._extract_identifiers(paper)

        for local_paper in self._local_paper_meta.values():
            local_pmcid, local_pmid, local_doi = self._extract_identifiers(local_paper)

            if pmcid and local_pmcid and pmcid == local_pmcid:
                return True
            if pmid and local_pmid and pmid == local_pmid:
                return True
            if doi and local_doi and doi == local_doi:
                return True

        return False

    def _search_local(self, query: str, top_k: int) -> List[Dict]:
        """
        本地论文搜索。
        """
        if self.local_searcher is None:
            return []

        try:
            results = self.local_searcher.search_papers(query, top_k=top_k)
            return [self._normalize_local_paper(r) for r in results]
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  本地搜索失败: {e}")
            return []

    def _search_online(self, query: str, max_results: int) -> List[Dict]:
        """
        在线论文搜索（PubMed + PMC）。
        """
        if self.online_searcher is None:
            return []

        try:
            results = self.online_searcher.search(
                query,
                max_results=max_results,
                search_pubmed=True,
                search_pmc=True,
            )
            return [self._normalize_online_result(r) for r in results]
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️  在线搜索失败: {e}")
            return []

    def search_papers(
        self,
        query: str,
        top_k: int = 20,
        use_online: Optional[bool] = None,
        online_max_results: Optional[int] = None,
    ) -> Dict:
        """
        混合搜索论文：本地 + 在线同时搜索，合并去重，统一排序。

        Args:
            query: 搜索关键词
            top_k: 返回的最大结果数
            use_online: 是否使用在线搜索（None 用初始化时的设置）
            online_max_results: 在线搜索每个数据库的最大结果数

        Returns:
            {
                "query": str,
                "total": int,              # 合并去重后的总数
                "local_count": int,        # 本地论文数
                "online_count": int,       # 在线新论文数（不在本地的）
                "online_in_local_count": int,  # 在线搜索到但已在本地的数量
                "papers": List[Dict],      # 合并后的论文列表（按 score 降序）
                "local_papers": List[Dict], # 仅本地论文
                "online_papers": List[Dict], # 仅在线新论文（不在本地的）
            }
        """
        if use_online is None:
            use_online = self.use_online
        if online_max_results is None:
            online_max_results = self.online_max_results

        if self.verbose:
            print(f"\n🔍 混合检索: '{query}' (top_k={top_k}, online={use_online})")

        # 并行搜索本地和在线（提速）
        local_results: List[Dict] = []
        online_results: List[Dict] = []

        if use_online and self.online_searcher is not None:
            # 并行执行
            with ThreadPoolExecutor(max_workers=2) as executor:
                local_future = executor.submit(self._search_local, query, top_k)
                online_future = executor.submit(self._search_online, query, online_max_results)

                local_results = local_future.result()
                online_results = online_future.result()
        else:
            local_results = self._search_local(query, top_k)

        if self.verbose:
            print(f"  📚 本地搜索: {len(local_results)} 篇")
            print(f"  🌐 在线搜索: {len(online_results)} 篇")

        # 统计在线论文中已在本地的数量
        online_in_local = sum(1 for r in online_results if r.get("in_local_db"))
        online_new = [r for r in online_results if not r.get("in_local_db")]

        if self.verbose:
            print(f"  🌐 在线论文中已在本地: {online_in_local} 篇")
            print(f"  🌐 在线新论文（不在本地）: {len(online_new)} 篇")

        # 合并去重：先放本地（优先保留本地版本），再放在线新的
        seen_identifiers = {"pmcid": set(), "pmid": set(), "doi": set()}
        merged: List[Dict] = []

        # 本地论文优先
        for paper in local_results:
            if not self._is_duplicate(paper, seen_identifiers):
                merged.append(paper)

        # 在线新论文（不在本地的）
        for paper in online_new:
            if not self._is_duplicate(paper, seen_identifiers):
                merged.append(paper)

        # 按相关性分数降序排序
        merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        # 截取 top_k
        merged = merged[:top_k]

        if self.verbose:
            print(f"  ✅ 合并去重后: {len(merged)} 篇 (本地 {len(local_results)} + 在线新 {len(online_new)})")

        return {
            "query": query,
            "total": len(merged),
            "local_count": len(local_results),
            "online_count": len(online_new),
            "online_in_local_count": online_in_local,
            "papers": merged,
            "local_papers": local_results,
            "online_papers": online_new,
        }


# 单例
_hybrid_retriever: Optional[HybridRetriever] = None


def get_hybrid_retriever(use_online: bool = True) -> HybridRetriever:
    """获取混合检索器单例。"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever(use_online=use_online)
    return _hybrid_retriever
