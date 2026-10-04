#!/usr/bin/env python3
"""
PMC (PubMed Central) 批量下载脚本 V1.0

遵循 NCBI E-utilities 官方规范：
  - ESearch: 搜索 PMC 开放获取论文，获取 PMCID 列表
  - EFetch:  按 PMCID 下载 PDF 全文
  - 限速:    无 API Key 3次/秒，有 API Key 10次/秒
  - 必须带:  tool 和 email 参数（NCBI 要求）

使用方法：
  # 按关键词搜索下载（默认50篇）
  python scripts/download_pmc.py --query "STAT1 interferon"

  # 下载200篇
  python scripts/download_pmc.py --query "JAK-STAT signaling" --max 200

  # 指定输出目录
  python scripts/download_pmc.py --query "immunology" --output documents/

  # 使用 API Key（提速到10次/秒）
  python scripts/download_pmc.py --query "cancer immunotherapy" --api-key YOUR_KEY

  # 从 PMCID 列表文件下载
  python scripts/download_pmc.py --pmid-list pmc_ids.txt

  # 只搜索不下载（预览结果）
  python scripts/download_pmc.py --query "STAT1" --dry-run

NCBI API Key 免费申请：https://www.ncbi.nlm.nih.gov/account/settings/
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

# 浏览器 User-Agent（S3 和某些 CDN 会拒绝空 UA 的请求）
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
}

# ============================================================
# NCBI E-utilities 配置
# ============================================================
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
S3_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"

# 工具标识（NCBI 要求每个请求带 tool 和 email）
DEFAULT_TOOL = "scipal-pmc-downloader"
DEFAULT_EMAIL = "chenwei-ucas@outlook.com"
DEFAULT_API_KEY = "76012a329673a2911604807c76294bf98507"

# 速率限制（秒/请求）
RATE_LIMIT_NO_KEY = 0.35   # 3次/秒 ≈ 0.33秒，留余量
RATE_LIMIT_WITH_KEY = 0.12  # 10次/秒 ≈ 0.1秒，留余量

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒


class PMCDownloader:
    """PMC 批量下载器，遵循 NCBI E-utilities 规范"""

    def __init__(
        self,
        tool: str = DEFAULT_TOOL,
        email: str = DEFAULT_EMAIL,
        api_key: str = None,
        output_dir: str = "documents",
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
        """限速等待，确保不超过 NCBI 规定的请求频率"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def _build_params(self, **kwargs) -> dict:
        """构建请求参数，自动添加 tool/email/api_key"""
        params = {
            "tool": self.tool,
            "email": self.email,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        params.update(kwargs)
        return params

    def _request(self, url: str, params: dict = None, stream: bool = False, timeout: int = 120):
        """发送 HTTP 请求，带重试和限速"""
        for attempt in range(MAX_RETRIES):
            self._rate_limit_wait()
            try:
                resp = requests.get(url, params=params, stream=stream, timeout=timeout,
                                    headers=BROWSER_HEADERS)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    # 限速触发，等久一点
                    wait = RETRY_DELAY * (attempt + 1)
                    if self.verbose:
                        print(f"  ⚠️  触发限速，等待 {wait} 秒后重试...")
                    time.sleep(wait)
                elif resp.status_code in (403, 404):
                    # 403/404 不重试，直接返回
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

    # ============================================================
    # 第一步：ESearch 搜索
    # ============================================================
    def search(self, query: str, max_results: int = 50) -> list[str]:
        """
        使用 ESearch 搜索 PMC 开放获取论文。

        Args:
            query: 搜索关键词
            max_results: 最大返回数量

        Returns:
            PMCID 列表（如 ["PMC1234567", ...]）
        """
        if self.verbose:
            print(f"🔍 搜索 PMC: {query}")
            print(f"   限制: 最多 {max_results} 篇，仅开放获取论文")

        # 构造搜索词：加开放获取过滤器
        search_term = f"{query} AND open access[filter]"

        # 第一次请求：拿总数
        params = self._build_params(
            db="pmc",
            term=search_term,
            retmax=0,  # 只要总数
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

        # 第二次请求：拿 ID 列表（分批获取）
        pmc_ids = []
        retmax = min(max_results, total)
        batch_size = 10000  # ESearch 单次最多返回这么多

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
            # PMC ID 格式：数字，需要加 PMC 前缀
            pmc_ids.extend([f"PMC{pid}" for pid in id_list])

        self.stats["searched"] = len(pmc_ids)
        if self.verbose:
            print(f"   获取到 {len(pmc_ids)} 个 PMCID")

        return pmc_ids[:max_results]

    # ============================================================
    # 第二步：获取论文元数据（ESummary）
    # ============================================================
    def fetch_metadata(self, pmc_ids: list[str]) -> dict:
        """
        使用 ESummary 获取论文元数据（标题、作者、期刊等）。

        Args:
            pmc_ids: PMCID 列表

        Returns:
            {pmc_id: {title, authors, journal, year, doi, ...}}
        """
        if not pmc_ids:
            return {}

        if self.verbose:
            print(f"📋 获取 {len(pmc_ids)} 篇论文的元数据...")

        metadata = {}
        batch_size = 200  # ESummary 单次最多处理这么多

        for i in range(0, len(pmc_ids), batch_size):
            batch = pmc_ids[i:i + batch_size]
            # 去掉 PMC 前缀，只传数字
            ids = [pid.replace("PMC", "") for pid in batch]

            params = self._build_params(
                db="pmc",
                id=",".join(ids),
                retmode="json",
            )
            resp = self._request(f"{EUTILS_BASE}/esummary.fcgi", params)
            if not resp:
                continue

            data = resp.json()
            result = data.get("result", {})

            for pmc_id in batch:
                numeric_id = pmc_id.replace("PMC", "")
                doc = result.get(numeric_id, {})
                if doc:
                    metadata[pmc_id] = {
                        "title": doc.get("title", ""),
                        "authors": [a.get("name", "") for a in doc.get("authors", [])],
                        "journal": doc.get("fulljournalname", doc.get("source", "")),
                        "year": doc.get("pubdate", "")[:4],
                        "doi": doc.get("elocationid", "").replace("doi:", ""),
                        "pmid": doc.get("pmid", ""),
                    }

        if self.verbose:
            print(f"   获取到 {len(metadata)} 篇的元数据")

        return metadata

    # ============================================================
    # 第三步：从 S3 查找并下载 PDF
    # ============================================================
    def _find_s3_pdf_path(self, pmc_id: str) -> str | None:
        """
        在 PMC OA S3 上查找论文的 PDF 路径。

        S3 目录结构：PMC{id}.{version}/PMC{id}.{version}.pdf
        大多数论文 version 是 .1，先尝试 .1，失败再搜索。

        Args:
            pmc_id: PMCID（如 "PMC13611828"）

        Returns:
            S3 相对路径，如 "PMC13611828.1/PMC13611828.1.pdf"
        """
        # 先尝试 version .1（绝大多数论文都是 .1）
        candidate = f"{pmc_id}.1/{pmc_id}.1.pdf"
        url = f"{S3_BASE}/{candidate}"
        for attempt in range(3):
            self._rate_limit_wait()
            try:
                resp = requests.head(url, timeout=30, allow_redirects=True,
                                     headers=BROWSER_HEADERS)
                if resp.status_code == 200:
                    return candidate
            except requests.RequestException:
                pass
            time.sleep(2)

        # .1 不行，用 S3 prefix 搜索找正确的 version
        for attempt in range(3):
            self._rate_limit_wait()
            try:
                list_url = f"{S3_BASE}/?list-type=2&prefix={pmc_id}&max-keys=20"
                resp = requests.get(list_url, timeout=30, headers=BROWSER_HEADERS)
                if resp.status_code == 200:
                    import re
                    keys = re.findall(r"<Key>([^<]+\.pdf)</Key>", resp.text)
                    if keys:
                        return keys[0]
            except requests.RequestException:
                pass
            time.sleep(2)

        return None

    def download_pdf(self, pmc_id: str) -> bool:
        """
        从 PMC OA S3 下载单篇论文的 PDF。

        这是 NCBI 官方推荐的批量下载方式之一，不需要 Proof-of-Work 验证。
        S3 bucket: pmc-oa-opendata

        Args:
            pmc_id: PMCID（如 "PMC13611828"）

        Returns:
            是否下载成功
        """
        # 输出文件名
        output_file = self.output_dir / f"{pmc_id}.pdf"

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
                output_file.unlink()

        # 在 S3 上查找 PDF 路径
        s3_path = self._find_s3_pdf_path(pmc_id)
        if not s3_path:
            if self.verbose:
                print(f"  ❌ {pmc_id} 在 S3 上未找到 PDF")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

        pdf_url = f"{S3_BASE}/{s3_path}"

        if self.verbose:
            print(f"  📥 下载 {pmc_id}...", end=" ", flush=True)

        resp = self._request(pdf_url, stream=True, timeout=120)
        if not resp:
            if self.verbose:
                print("❌ 下载失败")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

        # 检查内容类型
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
            if self.verbose:
                print(f"❌ 非 PDF 内容 ({content_type})")
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

        # 流式下载
        try:
            total_size = 0
            pdf_header_checked = False
            with open(output_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        # 检查文件头是否是 PDF（前 5 个字节应该是 %PDF-）
                        if not pdf_header_checked:
                            if not chunk.startswith(b"%PDF-"):
                                if self.verbose:
                                    print(f"❌ 不是 PDF 文件（开头是 {chunk[:20]!r}）")
                                output_file.unlink(missing_ok=True)
                                self.stats["failed"] += 1
                                self.stats["failed_ids"].append(pmc_id)
                                return False
                            pdf_header_checked = True
                        f.write(chunk)
                        total_size += len(chunk)

            # 验证下载的文件
            if total_size < 1024:
                if self.verbose:
                    print(f"❌ 文件太小 ({total_size}B)")
                output_file.unlink(missing_ok=True)
                self.stats["failed"] += 1
                self.stats["failed_ids"].append(pmc_id)
                return False

            if self.verbose:
                print(f"✅ ({total_size//1024}KB)")
            self.stats["downloaded"] += 1
            return True

        except Exception as e:
            if self.verbose:
                print(f"❌ 写入失败: {e}")
            output_file.unlink(missing_ok=True)
            self.stats["failed"] += 1
            self.stats["failed_ids"].append(pmc_id)
            return False

    # ============================================================
    # 批量下载
    # ============================================================
    def download_batch(self, pmc_ids: list[str], fetch_meta: bool = True) -> dict:
        """
        批量下载论文。

        Args:
            pmc_ids: PMCID 列表
            fetch_meta: 是否同时获取元数据

        Returns:
            统计信息
        """
        print(f"\n{'='*60}")
        print(f"📦 PMC 批量下载")
        print(f"{'='*60}")
        print(f"   论文数量: {len(pmc_ids)}")
        print(f"   输出目录: {self.output_dir.absolute()}")
        print(f"   API Key: {'已配置（10次/秒）' if self.api_key else '未配置（3次/秒）'}")
        print(f"{'='*60}\n")

        # 获取元数据（可选）
        metadata = {}
        if fetch_meta:
            metadata = self.fetch_metadata(pmc_ids)
            # 保存元数据
            meta_file = self.output_dir / "pmc_metadata.json"
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            print(f"   元数据已保存: {meta_file}\n")

        # 逐篇下载
        start_time = time.time()
        for i, pmc_id in enumerate(pmc_ids, 1):
            if self.verbose:
                print(f"[{i}/{len(pmc_ids)}]", end=" ")
            self.download_pdf(pmc_id)

        elapsed = time.time() - start_time

        # 打印报告
        self._print_report(elapsed)

        # 保存失败列表
        if self.stats["failed_ids"]:
            failed_file = self.output_dir / "pmc_failed_ids.txt"
            with open(failed_file, "w") as f:
                f.write("\n".join(self.stats["failed_ids"]))
            print(f"\n   失败列表已保存: {failed_file}")

        return self.stats

    def _print_report(self, elapsed: float):
        """打印下载报告"""
        print(f"\n{'='*60}")
        print(f"📊 下载报告")
        print(f"{'='*60}")
        print(f"   搜索到:   {self.stats['searched']} 篇")
        print(f"   下载成功: {self.stats['downloaded']} 篇")
        print(f"   跳过(已存在): {self.stats['skipped']} 篇")
        print(f"   下载失败: {self.stats['failed']} 篇")
        print(f"   总耗时:   {elapsed:.1f} 秒")
        if self.stats['downloaded'] > 0:
            print(f"   平均速度: {elapsed/max(self.stats['downloaded'],1):.1f} 秒/篇")
        print(f"{'='*60}")


# ============================================================
# 主函数
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="PMC (PubMed Central) 批量下载工具 - 遵循 NCBI E-utilities 规范",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 按关键词搜索下载50篇
  python scripts/download_pmc.py --query "STAT1 interferon"

  # 下载200篇到指定目录
  python scripts/download_pmc.py --query "JAK-STAT" --max 200 --output documents/

  # 使用 API Key 提速
  python scripts/download_pmc.py --query "immunology" --api-key YOUR_KEY

  # 从 PMCID 列表文件下载
  python scripts/download_pmc.py --pmid-list pmc_ids.txt

  # 只搜索不下载
  python scripts/download_pmc.py --query "cancer" --dry-run

NCBI API Key 免费申请: https://www.ncbi.nlm.nih.gov/account/settings/
        """,
    )

    # 搜索参数
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", "-q", type=str, help="搜索关键词（如 'STAT1 interferon'）")
    group.add_argument("--pmid-list", type=str, help="PMCID 列表文件路径（每行一个 PMCID）")

    # 下载参数
    parser.add_argument("--max", "-m", type=int, default=50, help="最大下载数量（默认50）")
    parser.add_argument("--output", "-o", type=str, default="documents", help="输出目录（默认 documents/）")
    parser.add_argument("--api-key", type=str, default=DEFAULT_API_KEY, help="NCBI API Key（提速到10次/秒）")
    parser.add_argument("--tool", type=str, default=DEFAULT_TOOL, help="工具标识（NCBI要求）")
    parser.add_argument("--email", type=str, default=DEFAULT_EMAIL, help="联系邮箱（NCBI要求，请改成你的）")

    # 行为参数
    parser.add_argument("--dry-run", action="store_true", help="只搜索不下载")
    parser.add_argument("--no-meta", action="store_true", help="不获取元数据")
    parser.add_argument("--quiet", "-s", action="store_true", help="静默模式，减少输出")

    args = parser.parse_args()

    # 初始化下载器
    downloader = PMCDownloader(
        tool=args.tool,
        email=args.email,
        api_key=args.api_key,
        output_dir=args.output,
        verbose=not args.quiet,
    )

    # 获取 PMCID 列表
    if args.query:
        pmc_ids = downloader.search(args.query, args.max)
    else:
        # 从文件读取
        list_file = Path(args.pmid_list)
        if not list_file.exists():
            print(f"❌ 文件不存在: {list_file}")
            sys.exit(1)
        pmc_ids = []
        with open(list_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # 统一格式：加 PMC 前缀
                    if not line.upper().startswith("PMC"):
                        line = f"PMC{line}"
                    pmc_ids.append(line)
        print(f"📋 从文件读取到 {len(pmc_ids)} 个 PMCID")

    if not pmc_ids:
        print("❌ 没有找到可下载的论文")
        sys.exit(0)

    # 只搜索不下载
    if args.dry_run:
        print(f"\n📋 预览模式（不下载）:")
        print(f"   找到 {len(pmc_ids)} 篇论文")
        for i, pmc_id in enumerate(pmc_ids[:10], 1):
            print(f"   {i}. {pmc_id}")
        if len(pmc_ids) > 10:
            print(f"   ... 还有 {len(pmc_ids)-10} 篇")
        print(f"\n   去掉 --dry-run 参数即可开始下载")
        return

    # 批量下载
    stats = downloader.download_batch(pmc_ids, fetch_meta=not args.no_meta)

    # 退出码
    if stats["failed"] > 0 and stats["downloaded"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
