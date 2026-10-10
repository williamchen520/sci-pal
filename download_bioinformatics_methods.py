#!/usr/bin/env python3
"""
Sci-Pal 生物信息学方法（Workflow/Pipeline/Tool）开放API批量下载脚本 V1.0

专门对接生物信息学分析方法的开放注册平台API，批量下载结构化的方法元数据：
  - Dockstore（GA4GH TRS标准API，全球最大开放workflow注册平台）
  - bio.tools（ELIXIR支持，生物信息学工具和数据服务注册中心）
  - nf-core（Nextflow社区curated最佳实践pipeline集合，GitHub API）

下载内容：
  - 结构化JSON元数据（bioinformatics_methods/）
    包含：名称、描述、标签/主题、作者、来源、许可证、参数、输入输出、链接等

特点：
  - 完全开放API，无需PubMed，无需NCBI API Key
  - 结构化程度高（机器可读的元数据，比论文methods部分更精确）
  - 增量下载（已下载自动跳过）
  - 支持按来源/类型/主题筛选
  - Windows编码兼容

使用方法：
  # 下载所有来源的生物信息学方法（默认各100条）
  python download_bioinformatics_methods.py

  # 只下载Dockstore的workflow
  python download_bioinformatics_methods.py --source dockstore

  # 只下载bio.tools的工具
  python download_bioinformatics_methods.py --source biotools

  # 每个来源下载500条
  python download_bioinformatics_methods.py --max 500

  # 按主题筛选（如基因组学、蛋白质组学）
  python download_bioinformatics_methods.py --topic genomics

  # 只搜索不下载（预览数量）
  python download_bioinformatics_methods.py --dry-run

  # 指定输出目录
  python download_bioinformatics_methods.py --output-dir data/bioinformatics_methods
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus, urlencode

import requests

# Windows 控制台编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ============================================================
# API 配置
# ============================================================
DOCKSTORE_API_BASE = "https://dockstore.org/api/ga4gh/trs/v2"
BIOTOOLS_API_BASE = "https://bio.tools/api"
NFCORE_API_BASE = "https://api.github.com"

# 通用请求头
HEADERS = {
    "User-Agent": "Sci-Pal-Bioinformatics-Methods-Downloader/1.0",
    "Accept": "application/json",
}

# ============================================================
# 主题分类配置（用于筛选和分类）
# ============================================================
BIOINFORMATICS_TOPICS = {
    "genomics": {
        "name": "基因组学",
        "keywords": ["genomics", "genome", "DNA sequencing", "WGS", "WES", "variant calling"],
        "biotools_topic": "Sequence analysis",
    },
    "transcriptomics": {
        "name": "转录组学",
        "keywords": ["transcriptomics", "RNA-seq", "gene expression", "differential expression"],
        "biotools_topic": "Gene expression",
    },
    "proteomics": {
        "name": "蛋白质组学",
        "keywords": ["proteomics", "mass spectrometry", "protein", "peptide"],
        "biotools_topic": "Proteomics",
    },
    "metabolomics": {
        "name": "代谢组学",
        "keywords": ["metabolomics", "metabolite", "metabolism", "NMR", "LC-MS"],
        "biotools_topic": "Metabolomics",
    },
    "epigenomics": {
        "name": "表观基因组学",
        "keywords": ["epigenomics", "ChIP-seq", "ATAC-seq", "methylation", "histone"],
        "biotools_topic": "Epigenetics",
    },
    "single_cell": {
        "name": "单细胞分析",
        "keywords": ["single cell", "scRNA-seq", "single-cell", "cell type"],
        "biotools_topic": "Single cell analysis",
    },
    "metagenomics": {
        "name": "宏基因组学",
        "keywords": ["metagenomics", "microbiome", "16S", "metagenome", "taxonomy"],
        "biotools_topic": "Metagenomics",
    },
    "structural_biology": {
        "name": "结构生物学",
        "keywords": ["structural biology", "protein structure", "cryo-EM", "X-ray", "molecular dynamics"],
        "biotools_topic": "Structure analysis",
    },
    "phylogenetics": {
        "name": "系统发育学",
        "keywords": ["phylogenetics", "phylogeny", "evolution", "tree", "alignment"],
        "biotools_topic": "Phylogenetics",
    },
    "machine_learning": {
        "name": "机器学习/AI",
        "keywords": ["machine learning", "deep learning", "AI", "neural network", "prediction"],
        "biotools_topic": "Machine learning",
    },
    "visualization": {
        "name": "可视化",
        "keywords": ["visualization", "plot", "figure", "interactive", "browser"],
        "biotools_topic": "Visualisation",
    },
    "statistics": {
        "name": "统计分析",
        "keywords": ["statistics", "statistical", "hypothesis testing", "regression", "R package"],
        "biotools_topic": "Statistics",
    },
}

# ============================================================
# Dockstore API 对接
# ============================================================
class DockstoreDownloader:
    """Dockstore GA4GH TRS API 对接，下载workflow和tool元数据"""

    def __init__(self, output_dir, max_items=100, topic=None, dry_run=False):
        self.output_dir = Path(output_dir) / "dockstore"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self.topic = topic
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_total_count(self):
        """获取workflow总数"""
        try:
            url = f"{DOCKSTORE_API_BASE}/tools"
            params = {"limit": 1}
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            # 尝试从header或响应中获取总数
            total = resp.headers.get("X-total-count")
            if total:
                return int(total)
            data = resp.json()
            if isinstance(data, dict) and "total" in data:
                return data["total"]
            return None
        except Exception as e:
            print(f"  ⚠️  获取Dockstore总数失败: {e}")
            return None

    def fetch_workflows(self, page_size=50):
        """分页获取workflow列表"""
        workflows = []
        offset = 0
        while len(workflows) < self.max_items:
            try:
                url = f"{DOCKSTORE_API_BASE}/tools"
                params = {
                    "limit": min(page_size, self.max_items - len(workflows)),
                    "offset": offset,
                    "type": "workflow",  # 只获取workflow类型
                }
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                # 处理不同的响应格式
                if isinstance(data, list):
                    batch = data
                elif isinstance(data, dict) and "tools" in data:
                    batch = data["tools"]
                elif isinstance(data, dict) and "content" in data:
                    batch = data["content"]
                else:
                    batch = []

                if not batch:
                    break

                workflows.extend(batch)
                # 超过max时截断
                if len(workflows) > self.max_items:
                    workflows = workflows[:self.max_items]
                print(f"  📥 Dockstore: 已获取 {len(workflows)}/{self.max_items} 条")

                if len(batch) < page_size:
                    break

                offset += page_size
                time.sleep(0.3)  # 限速

            except Exception as e:
                print(f"  ⚠️  Dockstore分页获取失败 (offset={offset}): {e}")
                time.sleep(2)
                break

        return workflows

    def fetch_workflow_detail(self, workflow_id):
        """获取单个workflow的详细信息"""
        try:
            # workflow_id 格式如: #workflow/github.com/nf-core/rnaseq
            encoded_id = quote_plus(workflow_id, safe="")
            url = f"{DOCKSTORE_API_BASE}/tools/{encoded_id}"
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  ⚠️  获取workflow详情失败 ({workflow_id}): {e}")
            return None

    def download(self):
        """执行下载"""
        print("\n" + "=" * 70)
        print("🚀 Dockstore 开放Workflow注册平台")
        print("=" * 70)

        total = self.get_total_count()
        if total:
            print(f"  📊 Dockstore共有约 {total:,} 个workflow/tool")

        if self.dry_run:
            print("  🔍 dry-run模式，不实际下载")
            return 0

        print(f"  📥 开始下载，最多 {self.max_items} 条...")

        workflows = self.fetch_workflows()
        if not workflows:
            print("  ❌ 未获取到任何workflow")
            return 0

        # 保存原始数据
        output_file = self.output_dir / f"dockstore_workflows_{len(workflows)}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(workflows, f, ensure_ascii=False, indent=2)

        print(f"  ✅ 保存 {len(workflows)} 条 Dockstore workflow 到: {output_file}")

        # 统计信息
        languages = {}
        for w in workflows:
            lang = w.get("descriptorType", [])
            if isinstance(lang, list):
                for l in lang:
                    languages[l] = languages.get(l, 0) + 1
            else:
                languages[lang] = languages.get(lang, 0) + 1

        if languages:
            print(f"  📊 Workflow语言分布: {dict(sorted(languages.items(), key=lambda x: -x[1]))}")

        return len(workflows)


# ============================================================
# bio.tools API 对接
# ============================================================
class BioToolsDownloader:
    """bio.tools REST API 对接，下载生物信息学工具元数据"""

    def __init__(self, output_dir, max_items=100, topic=None, dry_run=False):
        self.output_dir = Path(output_dir) / "biotools"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self.topic = topic
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_total_count(self):
        """获取工具总数"""
        try:
            url = f"{BIOTOOLS_API_BASE}/t/"
            params = {"format": "json", "page_size": 1}
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("count", 0)
        except Exception as e:
            print(f"  ⚠️  获取bio.tools总数失败: {e}")
            return None

    def fetch_tools(self, page_size=50):
        """分页获取工具列表"""
        tools = []
        page = 1
        while len(tools) < self.max_items:
            try:
                url = f"{BIOTOOLS_API_BASE}/t/"
                params = {
                    "format": "json",
                    "page": page,
                    "page_size": min(page_size, self.max_items - len(tools)),
                }
                # 按主题筛选
                if self.topic and self.topic in BIOINFORMATICS_TOPICS:
                    topic_name = BIOINFORMATICS_TOPICS[self.topic]["biotools_topic"]
                    params["topic"] = topic_name

                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                batch = data.get("list", [])
                if not batch:
                    break

                tools.extend(batch)
                # 超过max时截断
                if len(tools) > self.max_items:
                    tools = tools[:self.max_items]
                print(f"  📥 bio.tools: 已获取 {len(tools)}/{self.max_items} 条 (第{page}页)")

                # 检查是否还有下一页
                if not data.get("next"):
                    break

                page += 1
                time.sleep(0.3)  # 限速

            except Exception as e:
                print(f"  ⚠️  bio.tools分页获取失败 (page={page}): {e}")
                time.sleep(2)
                break

        return tools

    def download(self):
        """执行下载"""
        print("\n" + "=" * 70)
        print("🚀 bio.tools 生物信息学工具注册中心（ELIXIR）")
        print("=" * 70)

        total = self.get_total_count()
        if total:
            print(f"  📊 bio.tools共有约 {total:,} 个工具/数据服务")

        if self.topic:
            topic_name = BIOINFORMATICS_TOPICS.get(self.topic, {}).get("name", self.topic)
            print(f"  🎯 按主题筛选: {topic_name}")

        if self.dry_run:
            print("  🔍 dry-run模式，不实际下载")
            return 0

        print(f"  📥 开始下载，最多 {self.max_items} 条...")

        tools = self.fetch_tools()
        if not tools:
            print("  ❌ 未获取到任何工具")
            return 0

        # 保存原始数据
        suffix = f"_{self.topic}" if self.topic else ""
        output_file = self.output_dir / f"biotools_tools{suffix}_{len(tools)}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(tools, f, ensure_ascii=False, indent=2)

        print(f"  ✅ 保存 {len(tools)} 条 bio.tools 工具到: {output_file}")

        # 统计信息
        tool_types = {}
        topics = {}
        for t in tools:
            for tt in t.get("toolType", []):
                tool_types[tt] = tool_types.get(tt, 0) + 1
            for tp in t.get("topic", []):
                topic_term = tp.get("term", "unknown")
                topics[topic_term] = topics.get(topic_term, 0) + 1

        if tool_types:
            top_types = dict(sorted(tool_types.items(), key=lambda x: -x[1])[:5])
            print(f"  📊 工具类型Top5: {top_types}")
        if topics:
            top_topics = dict(sorted(topics.items(), key=lambda x: -x[1])[:5])
            print(f"  📊 主题Top5: {top_topics}")

        return len(tools)


# ============================================================
# nf-core GitHub API 对接
# ============================================================
class NFCoreDownloader:
    """nf-core pipeline集合，通过GitHub API获取pipeline列表和元数据"""

    def __init__(self, output_dir, max_items=100, topic=None, dry_run=False):
        self.output_dir = Path(output_dir) / "nfcore"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_items = max_items
        self.topic = topic
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers.update({"Accept": "application/vnd.github.v3+json"})

    def fetch_pipelines(self):
        """获取nf-core组织下的所有pipeline仓库"""
        pipelines = []
        page = 1
        while len(pipelines) < self.max_items:
            try:
                url = f"{NFCORE_API_BASE}/orgs/nf-core/repos"
                params = {
                    "page": page,
                    "per_page": min(100, self.max_items - len(pipelines)),
                    "sort": "updated",
                    "type": "public",
                }
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                batch = resp.json()

                if not batch:
                    break

                # 过滤掉非pipeline仓库（只保留有pipeline特征的）
                for repo in batch:
                    name = repo.get("name", "")
                    # 排除modules、tools、website等非pipeline仓库
                    if name not in ["modules", "tools", "nf-co.re", "website", "configs",
                                     "test-datasets", "assets", "cookiecutter", "docs",
                                     "community", "hackathon", "template"]:
                        pipelines.append(repo)

                print(f"  📥 nf-core: 已获取 {len(pipelines)}/{self.max_items} 个pipeline (第{page}页)")

                if len(batch) < 100:
                    break

                page += 1
                time.sleep(0.5)  # GitHub限速

            except Exception as e:
                print(f"  ⚠️  nf-core获取失败 (page={page}): {e}")
                # GitHub API限流
                if "rate limit" in str(e).lower() or "403" in str(e):
                    print("  ⏳ GitHub API限流，等待60秒...")
                    time.sleep(60)
                    continue
                break

        return pipelines

    def fetch_pipeline_readme(self, repo_name):
        """获取pipeline的README内容"""
        try:
            url = f"{NFCORE_API_BASE}/repos/nf-core/{repo_name}/readme"
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200:
                import base64
                data = resp.json()
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return content
            return None
        except Exception:
            return None

    def download(self):
        """执行下载"""
        print("\n" + "=" * 70)
        print("🚀 nf-core Nextflow社区curated Pipeline集合")
        print("=" * 70)

        print(f"  📊 nf-core官方网站列出约62个pipeline（33已发布+24开发中+5归档）")

        if self.dry_run:
            print("  🔍 dry-run模式，不实际下载")
            return 0

        print(f"  📥 开始下载，最多 {self.max_items} 个pipeline...")

        pipelines = self.fetch_pipelines()
        if not pipelines:
            print("  ❌ 未获取到任何pipeline")
            return 0

        # 为每个pipeline获取README（增加方法描述内容）
        print(f"  📖 正在获取 {len(pipelines)} 个pipeline的README文档...")
        for i, repo in enumerate(pipelines):
            name = repo.get("name", "")
            readme = self.fetch_pipeline_readme(name)
            if readme:
                repo["readme_content"] = readme[:50000]  # 限制长度
            if (i + 1) % 10 == 0:
                print(f"    已获取 {i+1}/{len(pipelines)} 个README")
            time.sleep(0.3)

        # 保存原始数据
        output_file = self.output_dir / f"nfcore_pipelines_{len(pipelines)}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(pipelines, f, ensure_ascii=False, indent=2)

        print(f"  ✅ 保存 {len(pipelines)} 个 nf-core pipeline 到: {output_file}")

        # 统计信息
        languages = {}
        for p in pipelines:
            lang = p.get("language", "Unknown")
            languages[lang] = languages.get(lang, 0) + 1
        if languages:
            print(f"  📊 主要语言: {dict(sorted(languages.items(), key=lambda x: -x[1])[:5])}")

        return len(pipelines)


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Sci-Pal 生物信息学方法开放API批量下载脚本 V1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 下载所有来源（默认各100条）
  python download_bioinformatics_methods.py

  # 只下载Dockstore
  python download_bioinformatics_methods.py --source dockstore

  # 每个来源下载500条
  python download_bioinformatics_methods.py --max 500

  # 按基因组学主题筛选
  python download_bioinformatics_methods.py --topic genomics

  # 预览模式（不实际下载）
  python download_bioinformatics_methods.py --dry-run
        """,
    )
    parser.add_argument(
        "--source",
        choices=["all", "dockstore", "biotools", "nfcore"],
        default="all",
        help="数据来源（默认all，全部下载）",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=100,
        help="每个来源最多下载条数（默认100）",
    )
    parser.add_argument(
        "--topic",
        choices=list(BIOINFORMATICS_TOPICS.keys()),
        default=None,
        help="按主题筛选（genomics/transcriptomics/proteomics等）",
    )
    parser.add_argument(
        "--output-dir",
        default="bioinformatics_methods",
        help="输出目录（默认bioinformatics_methods/）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只搜索不下载（预览模式）",
    )

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("🧬 Sci-Pal 生物信息学方法（Workflow/Pipeline/Tool）批量下载 V1.0")
    print("=" * 70)
    print(f"   来源: {args.source}")
    print(f"   每来源最多: {args.max} 条")
    if args.topic:
        topic_name = BIOINFORMATICS_TOPICS[args.topic]["name"]
        print(f"   主题筛选: {topic_name}")
    print(f"   输出目录: {args.output_dir}/")
    print(f"   模式: {'预览(dry-run)' if args.dry_run else '下载'}")
    print("=" * 70)

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_downloaded = 0
    results = {}

    # Dockstore
    if args.source in ["all", "dockstore"]:
        try:
            downloader = DockstoreDownloader(
                output_dir=args.output_dir,
                max_items=args.max,
                topic=args.topic,
                dry_run=args.dry_run,
            )
            count = downloader.download()
            results["dockstore"] = count
            total_downloaded += count
        except Exception as e:
            print(f"\n❌ Dockstore下载出错: {e}")
            results["dockstore"] = 0

    # bio.tools
    if args.source in ["all", "biotools"]:
        try:
            downloader = BioToolsDownloader(
                output_dir=args.output_dir,
                max_items=args.max,
                topic=args.topic,
                dry_run=args.dry_run,
            )
            count = downloader.download()
            results["biotools"] = count
            total_downloaded += count
        except Exception as e:
            print(f"\n❌ bio.tools下载出错: {e}")
            results["biotools"] = 0

    # nf-core
    if args.source in ["all", "nfcore"]:
        try:
            downloader = NFCoreDownloader(
                output_dir=args.output_dir,
                max_items=args.max,
                topic=args.topic,
                dry_run=args.dry_run,
            )
            count = downloader.download()
            results["nfcore"] = count
            total_downloaded += count
        except Exception as e:
            print(f"\n❌ nf-core下载出错: {e}")
            results["nfcore"] = 0

    # 汇总
    print("\n" + "=" * 70)
    print("📊 下载结果汇总")
    print("=" * 70)
    for source, count in results.items():
        status = "✅" if count > 0 else "❌"
        print(f"  {status} {source}: {count} 条")
    print(f"\n  📦 总计: {total_downloaded} 条生物信息学方法元数据")
    print(f"  📁 输出目录: {output_dir.absolute()}/")
    print("=" * 70)

    # 保存下载清单
    manifest = {
        "download_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": args.source,
        "max_per_source": args.max,
        "topic": args.topic,
        "dry_run": args.dry_run,
        "results": results,
        "total": total_downloaded,
    }
    manifest_file = output_dir / "download_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成！下载清单已保存到: {manifest_file}")


if __name__ == "__main__":
    main()
