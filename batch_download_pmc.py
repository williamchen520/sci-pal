#!/usr/bin/env python3
"""
PMC 全文一键批量下载脚本 V1.0

自动批量下载多个主题/期刊的 PMC 全文 XML，自动过滤只有摘要的文章，支持断点续传。

使用方法：
  # 用默认主题列表下载（免疫学+癌症+基因编辑等，每个主题100篇）
  python batch_download_pmc.py

  # 每个主题下载200篇
  python batch_download_pmc.py --max 200

  # 指定输出目录
  python batch_download_pmc.py --output documents_xml/

  # 只下载免疫学相关主题
  python batch_download_pmc.py --category immunology

  # 列出所有可用主题分类
  python batch_download_pmc.py --list
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# ============================================================
# 主题列表配置（可以自由增删）
# ============================================================
TOPICS = {
    "immunology": [
        "STAT1 interferon signaling",
        "JAK STAT pathway immunity",
        "innate immune response",
        "adaptive immunity T cell B cell",
        "cytokine signaling inflammation",
        "autoimmune disease mechanism",
        "vaccine immunology adjuvant",
        "immune checkpoint regulation",
    ],
    "cancer": [
        "cancer immunotherapy",
        "tumor microenvironment",
        "CAR T cell therapy",
        "cancer metastasis mechanism",
        "tumor immunology escape",
        "oncogene signaling pathway",
        "cancer stem cell",
        "chemotherapy resistance mechanism",
    ],
    "genomics": [
        "CRISPR Cas9 gene editing",
        "single cell RNA sequencing",
        "gene therapy clinical trial",
        "epigenetics DNA methylation",
        "genome wide association study",
        "transcriptomics gene regulation",
        "proteomics mass spectrometry",
        "spatial transcriptomics tissue",
    ],
    "molecular_biology": [
        "protein structure function",
        "signal transduction pathway",
        "gene expression regulation",
        "protein protein interaction",
        "cell signaling mechanism",
        "molecular mechanism disease",
        "RNA biology function",
        "DNA repair mechanism",
    ],
    "top_journals": [
        "journal:Cell",
        "journal:Nature",
        "journal:Science",
        "journal:Cancer Cell",
        "journal:Cell Stem Cell",
        "journal:Nature Medicine",
        "journal:Nature Biotechnology",
        "journal:Immunity",
        "journal:Neuron",
        "journal:Cell Metabolism",
    ],
}

# 默认下载所有分类
DEFAULT_CATEGORIES = ["immunology", "cancer", "genomics", "molecular_biology"]


def run_download(query: str, max_results: int, output_dir: str, no_filter: bool = False) -> dict:
    """
    运行单个主题的下载。

    Returns:
        dict: 下载统计结果
    """
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "download_pmc_xml.py"),
        "--query", query,
        "--max", str(max_results),
        "--output", output_dir,
    ]
    if no_filter:
        cmd.append("--no-filter")

    print(f"\n{'='*70}")
    print(f"📥 下载主题: {query}")
    print(f"   命令: {' '.join(cmd)}")
    print(f"{'='*70}")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max_results * 30 + 120,  # 每篇最多30秒，加2分钟缓冲
        )
        elapsed = time.time() - start_time

        # 打印输出
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"⚠️  STDERR: {result.stderr[:500]}")

        # 从输出中解析统计
        downloaded = 0
        filtered = 0
        failed = 0
        for line in result.stdout.split("\n"):
            if "下载成功" in line and "篇" in line:
                try:
                    downloaded = int(line.split(":")[1].strip().split("篇")[0].strip())
                except (ValueError, IndexError):
                    pass
            if "过滤掉" in line and "篇" in line:
                try:
                    filtered = int(line.split(":")[1].strip().split("篇")[0].strip())
                except (ValueError, IndexError):
                    pass
            if "下载失败" in line and "篇" in line:
                try:
                    failed = int(line.split(":")[1].strip().split("篇")[0].strip())
                except (ValueError, IndexError):
                    pass

        return {
            "query": query,
            "downloaded": downloaded,
            "filtered": filtered,
            "failed": failed,
            "elapsed": elapsed,
            "success": result.returncode == 0,
        }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"❌ 下载超时（{elapsed:.0f}秒）")
        return {
            "query": query,
            "downloaded": 0,
            "filtered": 0,
            "failed": 1,
            "elapsed": elapsed,
            "success": False,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 下载异常: {e}")
        return {
            "query": query,
            "downloaded": 0,
            "filtered": 0,
            "failed": 1,
            "elapsed": elapsed,
            "success": False,
        }


def main():
    parser = argparse.ArgumentParser(
        description="PMC 全文一键批量下载（自动过滤只有摘要的文章，支持断点续传）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--max", "-m", type=int, default=100, help="每个主题最大下载数量（默认100）")
    parser.add_argument("--output", "-o", type=str, default="documents_xml", help="输出目录")
    parser.add_argument("--category", "-c", type=str, nargs="+", default=None,
                        help="只下载指定分类（可用: immunology, cancer, genomics, molecular_biology, top_journals）")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用主题分类")
    parser.add_argument("--no-filter", action="store_true", help="不过滤只有摘要的文章")
    parser.add_argument("--dry-run", action="store_true", help="只列出要下载的主题，不实际下载")

    args = parser.parse_args()

    # 列出所有分类
    if args.list:
        print("\n📋 可用主题分类：")
        for category, topics in TOPICS.items():
            print(f"\n  【{category}】（{len(topics)} 个主题）")
            for i, topic in enumerate(topics, 1):
                print(f"    {i}. {topic}")
        print(f"\n💡 使用 --category 指定分类，如：python batch_download_pmc.py --category immunology cancer")
        return

    # 确定要下载的分类
    if args.category:
        categories = [c for c in args.category if c in TOPICS]
        if not categories:
            print(f"❌ 无效的分类: {args.category}")
            print(f"   可用分类: {', '.join(TOPICS.keys())}")
            sys.exit(1)
    else:
        categories = DEFAULT_CATEGORIES

    # 收集所有主题
    all_topics = []
    for category in categories:
        all_topics.extend(TOPICS[category])

    # 去重
    all_topics = list(dict.fromkeys(all_topics))

    print(f"\n{'='*70}")
    print(f"🚀 PMC 全文一键批量下载")
    print(f"{'='*70}")
    print(f"   分类: {', '.join(categories)}")
    print(f"   主题数: {len(all_topics)} 个")
    print(f"   每主题最多: {args.max} 篇")
    print(f"   预计最多: {len(all_topics) * args.max} 篇（过滤只有摘要后会更少）")
    print(f"   输出目录: {Path(args.output).absolute()}")
    print(f"   全文过滤: {'开启（只下载有全文的）' if not args.no_filter else '关闭'}")
    print(f"{'='*70}")

    if args.dry_run:
        print(f"\n📋 预览模式（不下载），将要下载的主题：")
        for i, topic in enumerate(all_topics, 1):
            print(f"   {i}. {topic}")
        return

    # 确认
    print(f"\n⚠️  即将开始下载，按 Ctrl+C 可随时中断。已下载的会自动跳过（断点续传）。")
    print(f"   等待 3 秒后开始...")
    time.sleep(3)

    # 逐个下载
    results = []
    total_start = time.time()

    for i, topic in enumerate(all_topics, 1):
        print(f"\n\n{'#'*70}")
        print(f"# 进度: [{i}/{len(all_topics)}] {topic}")
        print(f"{'#'*70}")

        result = run_download(topic, args.max, args.output, args.no_filter)
        results.append(result)

        # 简短汇总
        print(f"\n📊 本主题结果: 下载 {result['downloaded']} 篇 | 过滤 {result['filtered']} 篇 | 失败 {result['failed']} 篇 | 耗时 {result['elapsed']:.0f}秒")

        # 主题之间休息2秒，避免给 NCBI 太大压力
        if i < len(all_topics):
            time.sleep(2)

    total_elapsed = time.time() - total_start

    # 最终汇总
    total_downloaded = sum(r["downloaded"] for r in results)
    total_filtered = sum(r["filtered"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    success_count = sum(1 for r in results if r["success"])

    print(f"\n\n{'='*70}")
    print(f"🎉 批量下载完成！")
    print(f"{'='*70}")
    print(f"   主题总数:   {len(all_topics)} 个")
    print(f"   成功主题:   {success_count}/{len(all_topics)}")
    print(f"   下载成功:   {total_downloaded} 篇（有全文正文）")
    print(f"   过滤掉:     {total_filtered} 篇（只有摘要，无全文）")
    print(f"   下载失败:   {total_failed} 篇")
    print(f"   总耗时:     {total_elapsed/60:.1f} 分钟")
    if total_downloaded > 0:
        print(f"   平均速度:   {total_elapsed/total_downloaded:.1f} 秒/篇")
    print(f"   输出目录:   {Path(args.output).absolute()}")
    print(f"{'='*70}")

    # 失败的主题
    failed_topics = [r["query"] for r in results if not r["success"] or r["failed"] > 0]
    if failed_topics:
        print(f"\n⚠️  以下主题有失败，可以单独重跑：")
        for topic in failed_topics:
            print(f"   - {topic}")

    print(f"\n💡 下一步：运行 import_xml_v2.py 导入到数据库，然后构建向量索引")
    print(f"   python import_xml_v2.py --input {args.output}/ --output data/research.db")
    print(f"   python build_paragraph_vector_index.py")


if __name__ == "__main__":
    main()
