#!/usr/bin/env python3
"""
PMC (PubMed Central) 批量下载全文 XML 脚本 V1.0

遵循 NCBI E-utilities 官方规范：
  - ESearch: 搜索 PMC 开放获取论文，获取 PMCID 列表
  - EFetch:  按 PMCID 下载全文 XML
  - 限速:    无 API Key 3次/秒，有 API Key 10次/秒
  - 必须带:  tool 和 email 参数（NCBI 要求）

使用方法：
  # 按关键词搜索下载（默认50篇）
  python scripts/download_pmc_xml.py --query "STAT1 interferon"

  # 下载200篇
  python scripts/download_pmc_xml.py --query "JAK-STAT signaling" --max 200

  # 指定输出目录
  python scripts/download_pmc_xml.py --query "immunology" --output documents_xml/

  # 使用 API Key（提速到10次/秒）
  python scripts/download_pmc_xml.py --query "cancer immunotherapy" --api-key YOUR_KEY

NCBI API Key 免费申请：https://www.ncbi.nlm.nih.gov/account/settings/
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests

# ============================================================
# NCBI E-utilities 配置
# ============================================================
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 工具标识（NCBI 要求每个请求带 tool 和 email）
DEFAULT_TOOL = "scipal-pmc-xml-downloader"
DEFAULT_EMAIL = "chenwei-ucas@outlook.com"
DEFAULT_API_KEY = "76012a329673a2911604807c76294bf98507"

# 速率限制（秒/请求）
RATE_LIMIT_NO_KEY = 0.35   # 3次/秒 ≈ 0.33秒，留余量
RATE_LIMIT_WITH_KEY = 0.12  # 10次/秒 ≈ 0.1秒，留余量

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒


class PMCXMLDownloader:
    """PMC 批量下载全文 XML 器，遵循 NCBI E-utilities 规范"""

    def __init__(
        self,
        tool: str = DEFAULT_TOOL,
        email: str = DEFAULT_EMAIL,
        api_key: str = None,
        output_dir: str = "documents_xml",
        verbose: bool = True,
    ):
        self.tool = tool
        self.email = email
        self.api_key = api_key
        self.output_dir = Path(output_dir)
        self.verbose = verbose

        # 限速
        self.rate_limit = RATE_LIMIT_WITH_KEY if api_key else RATE_LIMIT_NO_KEY
        self.last_request_time = 0

        # 统计
        self.stats = {
            "searched": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "failed_ids": [],
        }

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit_wait(self):
        """等待速率限制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _build_params(self, **kwargs):
        """构建请求参数，自动加上 tool 和 email"""
        params = {
            "tool": self.tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(kwargs)
        return params

    def _request(self, url: str, params: dict = None, retries: int = MAX_RETRIES):
        """发送请求，带重试和速率限制"""
        for attempt in range(retries):
            self._rate_limit_wait()
            try:
                resp = requests.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp
                else:
                    if self.verbose:
                        print(f"  ⚠️  HTTP {resp.status_code}，{RETRY_DELAY}s 后重试...")
            except requests.RequestException as e:
                if self.verbose:
                    print(f"  ⚠️  请求失败（{e}），{RETRY_DELAY}s 后重试...")

            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)

        return None

    def search(self, query: str, max_results: int = 50) -> list[str]:
        """
        搜索 PMC，获取 PMCID 列表

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            PMCID 列表（如 ["PMC12345", "PMC67890"]）
        """
        if self.verbose:
            print(f"🔍 搜索: {query}（目标 {max_results} 篇）")

        pmc_ids = []
        batch_size = 100  # ESearch 单次最多返回这么多

        for start in range(0, max_results, batch_size):
            end = min(start + batch_size, max_results)
            search_term = f"{query}"

            params = self._build_params(
                db="pmc",
                term=search_term,
                retstart=start,
                retmax=end - start,
                retmode="json",
            )
            resp = self._request(f"{EUTILS_BASE}/esearch.fcgi", params)
            if not resp:
                break

            data = resp.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            # PMC ID 格式：数字，需要加 PMC 前缀
            pmc_ids.extend([f"PMC{pid}" for pid in id_list])

            self.stats["searched"] = len(pmc_ids)
            if self.verbose:
                print(f"   获取到 {len(pmc_ids)} 个 PMCID")

        return pmc_ids[:max_results]

    def download_xml(self, pmc_id: str) -> bool:
        """
        下载单篇论文的全文 XML

        Args:
            pmc_id: PMCID（如 "PMC13611828"）

        Returns:
            是否下载成功
        """
        # 输出文件名
        output_file = self.output_dir / f"{pmc_id}.xml"

        # 断点续传：已存在且大小合理就跳过
        if output_file.exists():
            size = output_file.stat().st_size
            if size > 1024:  # 大于 1KB 认为有效
                if self.verbose:
                    print(f"  ⏭️  {pmc_id} 已存在（{size//1024}KB），跳过")
                self.stats["skipped"] += 1
                return True
            else:
                if self.verbose:
                    print(f"  ⚠️  {pmc_id} 文件太小（{size}B），重新下载")

        # 下载 XML
        # 去掉 PMC 前缀，只传数字
        pmc_num = pmc_id.replace("PMC", "")

        params = self._build_params(
            db="pmc",
            id=pmc_num,
            retmode="xml",
        )

        if self.verbose:
            print(f"  ⬇️  下载 {pmc_id}...")

        resp = self._request(f"{EUTILS_BASE}/efetch.fcgi", params)
        if not resp:
            if self.verbose:
                print(f"  ❌ 下载 {pmc_id} 失败")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

        # 保存 XML
        try:
            output_file.write_bytes(resp.content)
            size = output_file.stat().st_size
            if self.verbose:
                print(f"  ✅ 下载 {pmc_id} 成功（{size//1024}KB）")
            self.stats["downloaded"] += 1
            return True
        except Exception as e:
            if self.verbose:
                print(f"  ❌ 保存 {pmc_id} 失败: {e}")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

    def download_batch(self, pmc_ids: list[str]) -> None:
        """
        批量下载 XML

        Args:
            pmc_ids: PMCID 列表
        """
        if self.verbose:
            print(f"\n📥 批量下载 {len(pmc_ids)} 篇论文的 XML...")

        for i, pmc_id in enumerate(pmc_ids, 1):
            if self.verbose:
                print(f"\n[{i}/{len(pmc_ids)}]")
            self.download_xml(pmc_id)

    def print_stats(self):
        """打印统计信息"""
        print(f"\n{'='*60}")
        print(f"✅ 下载完成！")
        print(f"{'='*60}")
        print(f"  搜索到: {self.stats['searched']} 篇")
        print(f"  新下载: {self.stats['downloaded']} 篇")
        print(f"  已存在跳过: {self.stats['skipped']} 篇")
        print(f"  失败: {self.stats['failed']} 篇")
        if self.stats["failed_ids"]:
            print(f"  失败列表: {self.stats['failed_ids']}")


def main():
    parser = argparse.ArgumentParser(description="PMC 批量下载全文 XML 脚本")
    parser.add_argument("--query", type=str, help="搜索关键词")
    parser.add_argument("--max", type=int, default=50, help="最大下载数（默认50）")
    parser.add_argument("--output", type=str, default="documents_xml", help="输出目录（默认 documents_xml/）")
    parser.add_argument("--api-key", type=str, default=None, help="NCBI API Key（可选，提速）")
    parser.add_argument("--dry-run", action="store_true", help="只搜索不下载")
    parser.add_argument("--pmid-list", type=str, help="从 PMCID 列表文件下载")

    args = parser.parse_args()

    downloader = PMCXMLDownloader(
        api_key=args.api_key,
        output_dir=args.output,
        verbose=True,
    )

    # 从文件读 PMCID 列表
    if args.pmid_list:
        with open(args.pmid_list, "r") as f:
            pmc_ids = [line.strip() for line in f if line.strip()]
        if downloader.verbose:
            print(f"📋 从文件读了 {len(pmc_ids)} 个 PMCID")
    # 搜索 PMCID
    elif args.query:
        pmc_ids = downloader.search(args.query, args.max)
    else:
        print("❌ 请指定 --query 或 --pmid-list")
        sys.exit(1)

    if args.dry_run:
        print(f"\n🔍 预览结果:")
        for pmc_id in pmc_ids[:10]:
            print(f"  {pmc_id}")
        if len(pmc_ids) > 10:
            print(f"  ... 还有 {len(pmc_ids) - 10} 个")
        return

    # 批量下载
    downloader.download_batch(pmc_ids)

    # 打印统计
    downloader.print_stats()


if __name__ == "__main__":
    main()
