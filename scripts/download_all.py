#!/usr/bin/env python3
"""
批量下载100篇论文（8个主题）
用法: python scripts\download_all.py
"""
from download_pmc import PMCDownloader, DEFAULT_API_KEY

TOPICS = [
    ("STAT1 interferon", 12),
    ("breast cancer immunology", 12),
    ("liver disease fibrosis", 12),
    ("hepatitis B virus HBV", 13),
    ("bioinformatics single cell RNA sequencing", 13),
    ("innate immunity macrophage", 13),
    ("pediatric immunology children", 12),
    ("primary immunodeficiency disease", 13),
]

def main():
    dl = PMCDownloader(
        api_key=DEFAULT_API_KEY,
        output_dir="documents",
        verbose=True,
    )

    for query, max_papers in TOPICS:
        print(f"\n{'='*60}")
        print(f"📚 主题: {query}（目标 {max_papers} 篇）")
        print(f"{'='*60}")
        pmc_ids = dl.search(query, max_papers)
        if pmc_ids:
            dl.download_batch(pmc_ids, fetch_meta=True)

    print(f"\n{'='*60}")
    print(f"✅ 全部下载完成！")
    print(f"{'='*60}")
    print(f"  新下载: {dl.stats['downloaded']} 篇")
    print(f"  已存在跳过: {dl.stats['skipped']} 篇")
    print(f"  失败: {dl.stats['failed']} 篇")
    if dl.stats['failed_ids']:
        print(f"  失败列表: {dl.stats['failed_ids']}")

if __name__ == "__main__":
    main()
