#!/usr/bin/env python3
"""
批量下载8个主题的全文 XML（每个主题100篇）
用法: python scripts\download_all_xml.py
"""
from download_pmc_xml import PMCXMLDownloader, DEFAULT_API_KEY

TOPICS = [
    ("STAT1 interferon", 100),
    ("breast cancer immunology", 100),
    ("liver disease fibrosis", 100),
    ("hepatitis B virus HBV", 100),
    ("bioinformatics", 100),
    ("innate immunity macrophage", 100),
    ("pediatric immunology children", 100),
    ("primary immunodeficiency disease", 100),
]

def main():
    dl = PMCXMLDownloader(
        api_key=DEFAULT_API_KEY,
        output_dir="documents_xml",
        verbose=True,
    )

    for query, max_papers in TOPICS:
        print(f"\n{'='*60}")
        print(f"📚 主题: {query}（目标 {max_papers} 篇）")
        print(f"{'='*60}")
        pmc_ids = dl.search(query, max_papers)
        if pmc_ids:
            dl.download_batch(pmc_ids)

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
