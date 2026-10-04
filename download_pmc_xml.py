#!/usr/bin/env python3
"""
PMC (PubMed Central) 批量下载 XML 脚本 V2.0

下载 JATS XML 格式的论文全文，而不是 PDF。

V2.0 新增：自动过滤只有摘要、没有全文正文的文章
  - 搜索时加 open access[filter]，从源头只搜开放获取论文
  - 下载后检查 XML 是否有 <body> 标签（有全文的标志）
  - 只有摘要的文章自动删除，不计入成功下载
  - 用 --no-filter 可关闭过滤

使用方法：
  # 按关键词搜索下载（默认100篇，自动过滤只有摘要的）
  python download_pmc_xml.py --query "STAT1 interferon"

  # 每个主题下载100篇
  python download_pmc_xml.py --query "JAK-STAT signaling" --max 100

  # 指定输出目录
  python download_pmc_xml.py --query "cancer immunotherapy" --output documents_xml/

  # 不过滤（下载所有文章，包括只有摘要的）
  python download_pmc_xml.py --query "STAT1" --no-filter

  # 只搜索不下载（预览结果）
  python download_pmc_xml.py --query "STAT1" --dry-run
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

# V2.1: Windows 控制台编码修复（cp1252 不支持 emoji 和中文，强制用 utf-8）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 浏览器 User-Agent
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/xml,*/*",
}

# NCBI E-utilities 配置
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 工具标识
DEFAULT_TOOL = "scipal-pmc-xml-downloader"
DEFAULT_EMAIL = "chenwei-ucas@outlook.com"
DEFAULT_API_KEY = "76012a329673a2911604807c76294bf98507"

# 速率限制
RATE_LIMIT_NO_KEY = 0.35
RATE_LIMIT_WITH_KEY = 0.12

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5


class PMCXMLDownloader:
    """PMC 批量下载 XML 全文"""

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

        self.rate_limit = RATE_LIMIT_WITH_KEY if api_key else RATE_LIMIT_NO_KEY
        self.last_request_time = 0

        self.stats = {
            "searched": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "filtered_no_fulltext": 0,  # V2: 过滤掉只有摘要、没有全文的文章
            "failed_ids": [],
        }
        self.filter_no_fulltext = True  # V2: 默认开启过滤只有摘要的文章

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _rate_limit_wait(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _build_params(self, **kwargs) -> dict:
        params = {
            "tool": self.tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(kwargs)
        return params

    def _request(self, url: str, params: dict = None, timeout: int = 120):
        for attempt in range(MAX_RETRIES):
            self._rate_limit_wait()
            try:
                resp = requests.get(url, params=params, timeout=timeout,
                                    headers=BROWSER_HEADERS)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    wait = RETRY_DELAY * (attempt + 1)
                    if self.verbose:
                        print(f"  ⚠️  触发限速，等待 {wait} 秒后重试...")
                    time.sleep(wait)
                elif resp.status_code in (403, 404):
                    if self.verbose:
                        print(f"  ⚠️  HTTP {resp.status_code}，不重试")
                    return None
                else:
                    if self.verbose:
                        print(f"  ⚠️  HTTP {resp.status_code}，重试 {attempt+1}/{MAX_RETRIES}")
                    time.sleep(RETRY_DELAY)
            except requests.RequestException as e:
                if self.verbose:
                    print(f"  ⚠️  请求异常: {e}，重试 {attempt+1}/{MAX_RETRIES}")
                time.sleep(RETRY_DELAY)
        return None

    def search(self, query: str, max_results: int = 100) -> list[str]:
        """搜索 PMC 开放获取论文"""
        if self.verbose:
            print(f"🔍 搜索 PMC: {query}")
            print(f"   限制: 最多 {max_results} 篇，仅开放获取论文")

        search_term = f"{query} AND open access[filter]"

        # 第一次请求：拿总数
        params = self._build_params(
            db="pmc",
            term=search_term,
            retmax=0,
            retmode="json",
        )
        resp = self._request(f"{EUTILS_BASE}/esearch.fcgi", params)
        if not resp:
            print("❌ 搜索失败")
            return []

        data = resp.json()
        total = int(data.get("esearchresult", {}).get("count", 0))
        if self.verbose:
            print(f"   找到 {total} 篇开放获取论文")

        if total == 0:
            return []

        # 第二次请求：拿 ID 列表
        pmc_ids = []
        retmax = min(max_results, total)
        batch_size = 10000

        for start in range(0, retmax, batch_size):
            end = min(start + batch_size, retmax)
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
            pmc_ids.extend([f"PMC{pid}" for pid in id_list])

        self.stats["searched"] = len(pmc_ids)
        if self.verbose:
            print(f"   获取到 {len(pmc_ids)} 个 PMCID")

        return pmc_ids[:max_results]

    def download_xml(self, pmc_id: str) -> bool:
        """下载单篇论文的 JATS XML 全文"""
        output_file = self.output_dir / f"{pmc_id}.xml"

        # 断点续传
        if output_file.exists():
            size = output_file.stat().st_size
            if size > 1024:
                if self.verbose:
                    print(f"  ⏭️  {pmc_id} 已存在（{size//1024}KB），跳过")
                self.stats["skipped"] += 1
                return True
            else:
                output_file.unlink()

        numeric_id = pmc_id.replace("PMC", "")

        if self.verbose:
            print(f"  📥 下载 {pmc_id}...", end=" ", flush=True)

        # 用 EFetch 获取 XML
        params = self._build_params(
            db="pmc",
            id=numeric_id,
            retmode="xml",
        )

        resp = self._request(f"{EUTILS_BASE}/efetch.fcgi", params, timeout=120)
        if not resp:
            if self.verbose:
                print("❌ 下载失败")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

        # 检查是不是 XML
        content_type = resp.headers.get("Content-Type", "")
        if "xml" not in content_type.lower() and "octet-stream" not in content_type.lower():
            if self.verbose:
                print(f"❌ 非 XML 内容 ({content_type})")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

        # 保存
        try:
            xml_content = resp.text

            # 简单验证：是不是 JATS XML（包含 <article> 标签）
            if "<article" not in xml_content and "<pmc-articleset" not in xml_content:
                if self.verbose:
                    print(f"❌ 不是有效的 JATS XML")
                self.stats["failed"] += 1
                self.stats["failed_ids"].append(pmc_id)
                return False

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(xml_content)

            size = len(xml_content)
            if size < 1024:
                if self.verbose:
                    print(f"❌ 文件太小 ({size}B)")
                output_file.unlink()
                self.stats["failed"] += 1
                self.stats["failed_ids"].append(pmc_id)
                return False

            # V2: 过滤只有摘要、没有全文正文的文章
            # JATS XML 里有全文的文章一定有 <body> 标签，只有摘要的文章只有 <front> 没有 <body>
            if self.filter_no_fulltext:
                has_body = "<body" in xml_content
                # 有些文章用 <body/> 自闭合标签（空 body），也算没有全文
                has_body_content = "<body>" in xml_content or ("<body " in xml_content and "</body>" in xml_content and "<body/>" not in xml_content)
                if not has_body or not has_body_content:
                    if self.verbose:
                        print(f"⚠️  只有摘要，无全文正文，已过滤")
                    output_file.unlink()
                    self.stats["filtered_no_fulltext"] += 1
                    return False

            if self.verbose:
                print(f"✅ ({size//1024}KB)")
            self.stats["downloaded"] += 1
            return True

        except Exception as e:
            if self.verbose:
                print(f"❌ 写入失败: {e}")
            output_file.unlink(missing_ok=True)
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

    def download_batch(self, pmc_ids: list[str]) -> dict:
        """批量下载 XML"""
        print(f"\n{'='*60}")
        print(f"📦 PMC XML 批量下载")
        print(f"{'='*60}")
        print(f"   论文数量: {len(pmc_ids)}")
        print(f"   输出目录: {self.output_dir.absolute()}")
        print(f"   API Key: {'已配置（10次/秒）' if self.api_key else '未配置（3次/秒）'}")
        print(f"{'='*60}\n")

        start_time = time.time()
        for i, pmc_id in enumerate(pmc_ids, 1):
            if self.verbose:
                print(f"[{i}/{len(pmc_ids)}]", end=" ")
            self.download_xml(pmc_id)

        elapsed = time.time() - start_time

        self._print_report(elapsed)

        if self.stats["failed_ids"]:
            failed_file = self.output_dir / "pmc_failed_ids.txt"
            with open(failed_file, "w") as f:
                f.write("\n".join(self.stats["failed_ids"]))
            print(f"\n   失败列表已保存: {failed_file}")

        return self.stats

    def _print_report(self, elapsed: float):
        print(f"\n{'='*60}")
        print(f"📊 下载报告")
        print(f"{'='*60}")
        print(f"   搜索到:   {self.stats['searched']} 篇")
        print(f"   下载成功: {self.stats['downloaded']} 篇（有全文正文）")
        print(f"   过滤掉:   {self.stats['filtered_no_fulltext']} 篇（只有摘要，无全文）")
        print(f"   跳过(已存在): {self.stats['skipped']} 篇")
        print(f"   下载失败: {self.stats['failed']} 篇")
        print(f"   总耗时:   {elapsed:.1f} 秒")
        if self.stats['downloaded'] > 0:
            print(f"   平均速度: {elapsed/max(self.stats['downloaded'],1):.1f} 秒/篇")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="PMC (PubMed Central) 批量下载 JATS XML 全文",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", "-q", type=str, help="搜索关键词")
    group.add_argument("--pmid-list", type=str, help="PMCID 列表文件路径")

    parser.add_argument("--max", "-m", type=int, default=100, help="最大下载数量（默认100）")
    parser.add_argument("--output", "-o", type=str, default="documents_xml", help="输出目录")
    parser.add_argument("--api-key", type=str, default=DEFAULT_API_KEY, help="NCBI API Key")
    parser.add_argument("--tool", type=str, default=DEFAULT_TOOL, help="工具标识")
    parser.add_argument("--email", type=str, default=DEFAULT_EMAIL, help="联系邮箱")
    parser.add_argument("--dry-run", action="store_true", help="只搜索不下载")
    parser.add_argument("--no-filter", action="store_true", help="不过滤只有摘要的文章（默认开启过滤，只下载有全文正文的）")

    args = parser.parse_args()

    downloader = PMCXMLDownloader(
        tool=args.tool,
        email=args.email,
        api_key=args.api_key,
        output_dir=args.output,
    )
    # V2: 设置是否过滤只有摘要的文章
    downloader.filter_no_fulltext = not args.no_filter
    if not args.no_filter:
        print("🔍 已开启全文过滤：只下载有完整正文的文章，自动过滤只有摘要的")
    else:
        print("⚠️  已关闭全文过滤：将下载所有文章（包括只有摘要的）")

    if args.query:
        pmc_ids = downloader.search(args.query, args.max)
    else:
        list_file = Path(args.pmid_list)
        if not list_file.exists():
            print(f"❌ 文件不存在: {list_file}")
            sys.exit(1)
        pmc_ids = []
        with open(list_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if not line.upper().startswith("PMC"):
                        line = f"PMC{line}"
                    pmc_ids.append(line)
        print(f"📋 从文件读取到 {len(pmc_ids)} 个 PMCID")

    if not pmc_ids:
        print("❌ 没有找到可下载的论文")
        sys.exit(0)

    if args.dry_run:
        print(f"\n📋 预览模式（不下载）:")
        print(f"   找到 {len(pmc_ids)} 篇论文")
        for i, pmc_id in enumerate(pmc_ids[:10], 1):
            print(f"   {i}. {pmc_id}")
        if len(pmc_ids) > 10:
            print(f"   ... 还有 {len(pmc_ids)-10} 篇")
        return

    stats = downloader.download_batch(pmc_ids)

    if stats["failed"] > 0 and stats["downloaded"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
