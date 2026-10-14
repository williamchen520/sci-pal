#!/usr/bin/env python3
"""
V25.19 - 检索参数调优脚本

用于在真实数据库上测试不同 MMR_LAMBDA、动态权重等参数的效果，
帮助选择最优配置。

用法:
    TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python3 scripts/tune_retrieval.py
    TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python3 scripts/tune_retrieval.py --top-k 10
    TRANSFORMERS_OFFLINE=1 HF_HUB_OFFLINE=1 python3 scripts/tune_retrieval.py --queries "STAT1 interferon" "JAK-STAT cancer" "single cell RNA sequencing"
"""

import argparse
import sys
from pathlib import Path
from collections import Counter

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# 标准测试查询（覆盖不同类型）
DEFAULT_QUERIES = [
    # 实体密集型（基因/蛋白符号多）
    "STAT1 interferon signaling pathway",
    "JAK-STAT activation in cancer immunotherapy",
    "SOCS1 negative feedback regulation",
    # 自然语言型（口语化、长查询）
    "How does the immune system respond to viral infection",
    "What is the role of macrophages in tumor microenvironment",
    # 技术短语型（方法/技术术语）
    "single cell RNA sequencing batch effects correction",
    "mass cytometry data analysis pipeline",
    "CRISPR Cas9 gene editing off-target effects",
]


def compute_diversity_metrics(paragraphs: list) -> dict:
    """计算检索结果的多样性指标。"""
    if not paragraphs:
        return {
            "count": 0,
            "unique_papers": 0,
            "max_paper_ratio": 0.0,
            "avg_score": 0.0,
            "score_range": (0.0, 0.0),
        }

    paper_ids = [p.get("paper_id", "?") for p in paragraphs]
    unique_papers = len(set(paper_ids))
    paper_counts = Counter(paper_ids)
    max_paper_count = max(paper_counts.values())
    max_paper_ratio = max_paper_count / len(paragraphs)

    scores = [p.get("rerank_score", p.get("rrf_score", 0.0)) for p in paragraphs]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    score_range = (min(scores) if scores else 0.0, max(scores) if scores else 0.0)

    return {
        "count": len(paragraphs),
        "unique_papers": unique_papers,
        "max_paper_ratio": max_paper_ratio,
        "avg_score": avg_score,
        "score_range": score_range,
    }


def test_lambda_value(retriever, queries: list, lambda_val: float, top_k: int) -> dict:
    """测试单个 MMR_LAMBDA 值的效果。"""
    # 临时修改 MMR_LAMBDA
    original_lambda = retriever.searcher.mmr.lambda_param
    retriever.searcher.mmr.lambda_param = lambda_val

    all_metrics = []
    for query in queries:
        try:
            result = retriever.retrieve(query, top_paragraphs=top_k)
            metrics = compute_diversity_metrics(result.get("paragraphs", []))
            all_metrics.append(metrics)
        except Exception as e:
            print(f"  ⚠️  查询失败: {query[:40]}... ({e})")

    # 恢复原始值
    retriever.searcher.mmr.lambda_param = original_lambda

    # 聚合指标
    if not all_metrics:
        return {"lambda": lambda_val, "avg_unique_papers": 0, "avg_max_ratio": 1.0, "avg_score": 0.0}

    avg_unique = sum(m["unique_papers"] for m in all_metrics) / len(all_metrics)
    avg_max_ratio = sum(m["max_paper_ratio"] for m in all_metrics) / len(all_metrics)
    avg_score = sum(m["avg_score"] for m in all_metrics) / len(all_metrics)

    return {
        "lambda": lambda_val,
        "queries_tested": len(all_metrics),
        "avg_unique_papers": round(avg_unique, 2),
        "avg_max_ratio": round(avg_max_ratio, 3),
        "avg_score": round(avg_score, 4),
    }


def print_results_table(results: list):
    """打印对比结果表格。"""
    print("\n" + "=" * 80)
    print("📊 MMR_LAMBDA 参数对比结果")
    print("=" * 80)
    print(f"{'λ':>6} | {'查询数':>6} | {'平均论文数':>10} | {'最大论文占比':>12} | {'平均相关分':>10} | 评价")
    print("-" * 80)

    for r in results:
        # 评价：多样性（论文数多、占比低）vs 相关性（分数高）的平衡
        diversity_score = r["avg_unique_papers"] * (1 - r["avg_max_ratio"])
        if r["lambda"] == 1.0:
            eval_str = "纯相关性（无MMR）"
        elif r["lambda"] >= 0.8:
            eval_str = "偏相关性"
        elif r["lambda"] >= 0.6:
            eval_str = "平衡（推荐）"
        else:
            eval_str = "偏多样性"

        print(f"{r['lambda']:>6.1f} | {r['queries_tested']:>6} | "
              f"{r['avg_unique_papers']:>10.2f} | "
              f"{r['avg_max_ratio']:>12.1%} | "
              f"{r['avg_score']:>10.4f} | {eval_str}")

    print("=" * 80)


def print_recommendation(results: list):
    """给出参数推荐。"""
    if not results:
        return

    # 找到平衡最好的参数（论文数多 + 占比低 + 分数不太低）
    best_balance = None
    best_score = -1

    for r in results:
        if r["lambda"] == 1.0:
            continue  # 跳过无MMR的基线
        # 综合评分：多样性权重 0.6，相关性权重 0.4
        diversity = r["avg_unique_papers"] * (1 - r["avg_max_ratio"])
        max_diversity = max(rr["avg_unique_papers"] * (1 - rr["avg_max_ratio"]) for rr in results if rr["lambda"] != 1.0)
        normalized_diversity = diversity / max_diversity if max_diversity > 0 else 0

        max_score = max(rr["avg_score"] for rr in results)
        normalized_score = r["avg_score"] / max_score if max_score > 0 else 0

        combined = 0.6 * normalized_diversity + 0.4 * normalized_score
        if combined > best_score:
            best_score = combined
            best_balance = r

    print("\n💡 参数推荐:")
    if best_balance:
        print(f"  推荐 MMR_LAMBDA = {best_balance['lambda']}")
        print(f"  理由: 多样性与相关性的最佳平衡")
        print(f"  预期效果: 平均涉及 {best_balance['avg_unique_papers']} 篇论文，"
              f"最大论文占比 {best_balance['avg_max_ratio']:.1%}")
    print("\n📝 调参建议:")
    print("  - 如果发现返回结果大量来自同一篇论文 → 降低 λ（如 0.5-0.6）")
    print("  - 如果发现返回结果相关性下降明显 → 提高 λ（如 0.8-0.9）")
    print("  - λ = 1.0 完全关闭 MMR 多样性去重，纯按相关性排序")
    print("  - 修改位置: services/search/hybrid_search.py 顶部的 MMR_LAMBDA 常量")


def main():
    parser = argparse.ArgumentParser(description="V25.19 检索参数调优脚本")
    parser.add_argument("--top-k", type=int, default=10, help="每个查询返回的段落数（默认 10）")
    parser.add_argument("--queries", nargs="+", default=None, help="自定义测试查询列表")
    parser.add_argument("--lambdas", nargs="+", type=float,
                        default=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
                        help="要测试的 MMR_LAMBDA 值列表")
    args = parser.parse_args()

    queries = args.queries if args.queries else DEFAULT_QUERIES

    print("=" * 80)
    print("🔧 V25.19 检索参数调优")
    print("=" * 80)
    print(f"测试查询数: {len(queries)}")
    print(f"返回段落数: {args.top_k}")
    print(f"测试 λ 值: {args.lambdas}")
    print()

    # 初始化检索器
    print("⏳ 初始化检索器（加载模型可能需要几秒）...")
    try:
        from services.search.unified_retriever import UnifiedRetriever
        retriever = UnifiedRetriever(rerank=True, routing=True, expand=True)
    except Exception as e:
        print(f"❌ 检索器初始化失败: {e}")
        sys.exit(1)

    print("✅ 检索器初始化完成")
    print()

    # 测试每个 λ 值
    results = []
    for lambda_val in args.lambdas:
        print(f"▶ 测试 MMR_LAMBDA = {lambda_val}...")
        result = test_lambda_value(retriever, queries, lambda_val, args.top_k)
        results.append(result)
        print(f"  完成: 平均论文数={result['avg_unique_papers']}, "
              f"最大占比={result['avg_max_ratio']:.1%}, "
              f"平均相关分={result['avg_score']:.4f}")

    # 打印结果
    print_results_table(results)
    print_recommendation(results)

    print("\n✅ 调优完成。根据上面的结果修改 hybrid_search.py 中的 MMR_LAMBDA 即可。")


if __name__ == "__main__":
    main()
