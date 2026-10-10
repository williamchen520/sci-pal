"""
Sci-Pal 检索可观测性模块 V33.5

用途：记录每次检索的完整链路信息，方便调试召回率、重排效果、最终入选证据来源。
- 记录：query、扩展词、实体、各路召回、重排分数、最终入选、各阶段耗时
- 查询：按 task_id / review_id 查询历史检索记录
- 统计：召回率、重排前后排名变化、各路召回贡献占比

设计原则：
- 低开销：记录操作异步/非阻塞，不影响检索性能
- 可追溯：每条记录都有唯一 ID 和时间戳
- 可分析：提供统计接口，方便定位"召回不到"还是"重排排错"
"""

import json
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class RecallChannelResult:
    """单路召回结果"""
    channel: str = ""  # vector / bm25 / entity / graph / abstract
    count: int = 0  # 召回数量
    top_ids: list[str] = field(default_factory=list)  # Top 10 的 paper_id/para_id
    avg_score: float = 0.0  # 平均分数
    max_score: float = 0.0  # 最高分数


@dataclass
class RetrievalTiming:
    """检索各阶段耗时（毫秒）"""
    total: float = 0.0
    query_expansion: float = 0.0
    entity_extraction: float = 0.0
    vector_recall: float = 0.0
    bm25_recall: float = 0.0
    entity_recall: float = 0.0
    graph_traversal: float = 0.0
    abstract_search: float = 0.0
    rerank: float = 0.0
    mmr_diversity: float = 0.0
    evidence_extraction: float = 0.0


@dataclass
class RetrievalRecord:
    """单次检索的完整记录"""
    # 基本信息
    record_id: str = field(default_factory=lambda: f"ret_{uuid.uuid4().hex[:12]}")
    task_id: str = ""
    review_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    timestamp_unix: float = field(default_factory=time.time)

    # 查询信息
    original_query: str = ""
    expanded_queries: list[str] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    entity_hits: dict[str, int] = field(default_factory=dict)  # 每个实体命中数

    # 召回信息
    recall_channels: dict[str, RecallChannelResult] = field(default_factory=dict)
    hybrid_recall_count: int = 0  # 混合召回后总数
    hybrid_recall_top_ids: list[str] = field(default_factory=list)

    # 重排信息
    rerank_model: str = "bge-reranker-base"
    rerank_input_count: int = 0
    rerank_output_count: int = 0
    rerank_scores: dict[str, float] = field(default_factory=dict)  # para_id -> score
    rerank_top_10: list[tuple[str, float]] = field(default_factory=list)  # (para_id, score)

    # MMR 多样性选择
    mmr_input_count: int = 0
    mmr_output_count: int = 0
    mmr_lambda: float = 0.5

    # 最终结果
    final_paragraph_count: int = 0
    final_evidence_count: int = 0
    final_paper_ids: list[str] = field(default_factory=list)
    final_evidence_ids: list[str] = field(default_factory=list)

    # 摘要库搜索
    abstract_search_count: int = 0
    abstract_search_error: str = ""

    # 耗时
    timing: RetrievalTiming = field(default_factory=RetrievalTiming)

    # 元数据
    section_title: str = ""  # 如果是按章节检索，记录章节标题
    review_type: str = ""  # narrative / systematic / comparative
    max_papers: int = 0

    # 备注
    notes: str = ""

    def to_dict(self) -> dict:
        """转换为可序列化的 dict"""
        d = asdict(self)
        # 处理 tuple 类型（rerank_top_10）
        d["rerank_top_10"] = [list(x) for x in self.rerank_top_10]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RetrievalRecord":
        """从 dict 恢复"""
        # 处理嵌套结构
        if "recall_channels" in d:
            d["recall_channels"] = {
                k: RecallChannelResult(**v) for k, v in d["recall_channels"].items()
            }
        if "timing" in d:
            d["timing"] = RetrievalTiming(**d["timing"])
        if "rerank_top_10" in d:
            d["rerank_top_10"] = [tuple(x) for x in d["rerank_top_10"]]
        return cls(**d)


@dataclass
class RetrievalStats:
    """检索统计信息"""
    total_records: int = 0
    time_range_start: str = ""
    time_range_end: str = ""

    # 召回统计
    avg_hybrid_recall: float = 0.0
    avg_vector_recall: float = 0.0
    avg_bm25_recall: float = 0.0
    avg_entity_recall: float = 0.0

    # 重排统计
    avg_rerank_input: float = 0.0
    avg_rerank_output: float = 0.0
    avg_rerank_top_score: float = 0.0

    # 最终结果统计
    avg_final_paragraphs: float = 0.0
    avg_final_evidence: float = 0.0

    # 各路召回贡献占比（最终入选证据中，来自各路的比例）
    channel_contribution: dict[str, float] = field(default_factory=dict)

    # 耗时统计
    avg_total_time_ms: float = 0.0
    avg_rerank_time_ms: float = 0.0

    # 异常统计
    abstract_search_error_count: int = 0
    zero_result_count: int = 0  # 最终结果为 0 的次数


# =============================================================================
# 检索可观测性管理器
# =============================================================================

class RetrievalObservability:
    """
    检索可观测性管理器

    用法：
        obs = RetrievalObservability()
        record = obs.start_record(task_id="...", query="STAT1 immunity")
        # ... 执行检索 ...
        record.recall_channels["vector"] = RecallChannelResult(...)
        record.final_evidence_count = 50
        obs.finish_record(record)

        # 查询
        record = obs.get_record("ret_xxx")
        stats = obs.get_stats(last_n=100)
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_records: int = 1000,
        enabled: bool = True,
    ):
        """
        Args:
            storage_dir: 存储目录，默认 data/retrieval_logs/
            max_records: 最多保留的记录数（超过后删除最旧的）
            enabled: 是否启用（生产环境可关闭以减少开销）
        """
        self.enabled = enabled
        self.max_records = max_records
        self._lock = threading.Lock()
        self._cache: dict[str, RetrievalRecord] = {}  # 内存缓存

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "retrieval_logs"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 索引文件（记录所有 record_id 和时间戳，方便快速查询）
        self._index_file = self.storage_dir / "index.json"
        self._index: list[dict] = self._load_index()

    # -------------------------------------------------------------------------
    # 记录管理
    # -------------------------------------------------------------------------

    def start_record(
        self,
        task_id: str = "",
        review_id: str = "",
        query: str = "",
        section_title: str = "",
        review_type: str = "",
        max_papers: int = 0,
    ) -> RetrievalRecord:
        """开始一次检索记录（创建记录并返回，调用方填充各字段后调用 finish_record）"""
        if not self.enabled:
            return RetrievalRecord()  # 返回空记录，不存储

        record = RetrievalRecord(
            task_id=task_id,
            review_id=review_id,
            original_query=query,
            section_title=section_title,
            review_type=review_type,
            max_papers=max_papers,
        )
        record.timing.total = time.time()  # 记录开始时间（后面会算差值）
        return record

    def finish_record(self, record: RetrievalRecord) -> str:
        """完成一次检索记录（计算总耗时，保存到缓存和磁盘）"""
        if not self.enabled:
            return record.record_id

        # 计算总耗时
        if record.timing.total > 0:
            record.timing.total = (time.time() - record.timing.total) * 1000  # 转毫秒

        # 保存到内存缓存
        with self._lock:
            self._cache[record.record_id] = record

            # 更新索引
            self._index.append({
                "record_id": record.record_id,
                "task_id": record.task_id,
                "review_id": record.review_id,
                "timestamp": record.timestamp,
                "timestamp_unix": record.timestamp_unix,
                "original_query": record.original_query[:100],  # 截断，避免索引过大
                "section_title": record.section_title[:100],
                "final_evidence_count": record.final_evidence_count,
            })

            # 限制索引大小
            if len(self._index) > self.max_records:
                # 删除最旧的记录
                old_records = self._index[:-self.max_records]
                for old in old_records:
                    self._delete_record_file(old["record_id"])
                    self._cache.pop(old["record_id"], None)
                self._index = self._index[-self.max_records:]

            # 保存索引
            self._save_index()

        # 保存记录到磁盘
        self._save_record(record)

        return record.record_id

    def get_record(self, record_id: str) -> Optional[RetrievalRecord]:
        """按 record_id 查询检索记录"""
        # 先查缓存
        with self._lock:
            if record_id in self._cache:
                return self._cache[record_id]

        # 再查磁盘
        record_file = self.storage_dir / f"{record_id}.json"
        if record_file.is_file():
            try:
                with open(record_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                record = RetrievalRecord.from_dict(data)
                # 加入缓存
                with self._lock:
                    self._cache[record_id] = record
                return record
            except Exception as e:
                print(f"⚠️  读取检索记录失败 {record_id}: {e}")
        return None

    def get_by_task_id(self, task_id: str) -> list[RetrievalRecord]:
        """按 task_id 查询所有相关检索记录"""
        results = []
        with self._lock:
            for idx in self._index:
                if idx.get("task_id") == task_id:
                    record = self.get_record(idx["record_id"])
                    if record:
                        results.append(record)
        # 按时间排序
        results.sort(key=lambda r: r.timestamp_unix)
        return results

    def get_by_review_id(self, review_id: str) -> list[RetrievalRecord]:
        """按 review_id 查询所有相关检索记录"""
        results = []
        with self._lock:
            for idx in self._index:
                if idx.get("review_id") == review_id:
                    record = self.get_record(idx["record_id"])
                    if record:
                        results.append(record)
        results.sort(key=lambda r: r.timestamp_unix)
        return results

    def list_recent(self, n: int = 20) -> list[RetrievalRecord]:
        """列出最近的 n 条检索记录"""
        with self._lock:
            recent_idx = self._index[-n:] if len(self._index) > n else self._index[:]
        results = []
        for idx in reversed(recent_idx):  # 最新的在前
            record = self.get_record(idx["record_id"])
            if record:
                results.append(record)
        return results

    # -------------------------------------------------------------------------
    # 统计分析
    # -------------------------------------------------------------------------

    def get_stats(self, last_n: int = 100) -> RetrievalStats:
        """
        获取最近 N 条记录的统计信息

        统计维度：
        - 平均召回数（各路 + 混合）
        - 平均重排输入/输出
        - 平均最终证据数
        - 各路召回贡献占比
        - 平均耗时
        - 异常统计
        """
        recent = self.list_recent(last_n)
        if not recent:
            return RetrievalStats()

        stats = RetrievalStats(
            total_records=len(recent),
            time_range_start=recent[-1].timestamp if recent else "",
            time_range_end=recent[0].timestamp if recent else "",
        )

        # 累加统计
        total_hybrid = 0
        total_vector = 0
        total_bm25 = 0
        total_entity = 0
        total_rerank_input = 0
        total_rerank_output = 0
        total_rerank_top_score = 0
        total_final_paragraphs = 0
        total_final_evidence = 0
        total_time = 0
        total_rerank_time = 0
        abstract_errors = 0
        zero_results = 0

        # 各路召回贡献（最终入选证据中，来自各路的比例）
        channel_contribution = defaultdict(int)

        for record in recent:
            total_hybrid += record.hybrid_recall_count
            total_rerank_input += record.rerank_input_count
            total_rerank_output += record.rerank_output_count
            total_final_paragraphs += record.final_paragraph_count
            total_final_evidence += record.final_evidence_count
            total_time += record.timing.total
            total_rerank_time += record.timing.rerank

            if record.rerank_top_10:
                total_rerank_top_score += record.rerank_top_10[0][1]

            if record.abstract_search_error:
                abstract_errors += 1

            if record.final_evidence_count == 0:
                zero_results += 1

            # 各路召回
            for channel, result in record.recall_channels.items():
                if channel == "vector":
                    total_vector += result.count
                elif channel == "bm25":
                    total_bm25 += result.count
                elif channel == "entity":
                    total_entity += result.count
                channel_contribution[channel] += result.count

        n = len(recent)
        stats.avg_hybrid_recall = total_hybrid / n
        stats.avg_vector_recall = total_vector / n
        stats.avg_bm25_recall = total_bm25 / n
        stats.avg_entity_recall = total_entity / n
        stats.avg_rerank_input = total_rerank_input / n
        stats.avg_rerank_output = total_rerank_output / n
        stats.avg_rerank_top_score = total_rerank_top_score / n if n > 0 else 0
        stats.avg_final_paragraphs = total_final_paragraphs / n
        stats.avg_final_evidence = total_final_evidence / n
        stats.avg_total_time_ms = total_time / n
        stats.avg_rerank_time_ms = total_rerank_time / n
        stats.abstract_search_error_count = abstract_errors
        stats.zero_result_count = zero_results

        # 各路召回贡献占比
        total_channel = sum(channel_contribution.values())
        if total_channel > 0:
            stats.channel_contribution = {
                k: round(v / total_channel * 100, 1)
                for k, v in sorted(channel_contribution.items(), key=lambda x: -x[1])
            }

        return stats

    # -------------------------------------------------------------------------
    # 调试辅助
    # -------------------------------------------------------------------------

    def analyze_retrieval(self, record_id: str) -> dict:
        """
        深度分析单次检索，定位问题

        返回：
        - status: good / warning / critical
        - issues: 问题列表
        - suggestions: 改进建议
        - summary: 简要总结
        """
        record = self.get_record(record_id)
        if not record:
            return {"status": "error", "issues": ["记录不存在"], "suggestions": [], "summary": ""}

        issues = []
        suggestions = []

        # 检查召回是否充足
        if record.hybrid_recall_count < 10:
            issues.append(f"混合召回数过少：{record.hybrid_recall_count}")
            suggestions.append("检查 query 是否过于具体，尝试扩展查询词")
        elif record.hybrid_recall_count > 500:
            issues.append(f"混合召回数过多：{record.hybrid_recall_count}，可能影响重排效率")
            suggestions.append("考虑增加 MMR 多样性选择的严格度")

        # 检查各路召回是否均衡
        vector_count = record.recall_channels.get("vector", RecallChannelResult()).count
        bm25_count = record.recall_channels.get("bm25", RecallChannelResult()).count
        if vector_count == 0 and bm25_count == 0:
            issues.append("向量和 BM25 召回都为 0")
            suggestions.append("检查向量库和 FTS5 索引是否正常")
        elif vector_count > 0 and bm25_count == 0:
            issues.append("BM25 召回为 0，只有向量召回")
            suggestions.append("检查 FTS5 查询语法，可能是关键词被当作列名")

        # 检查重排
        if record.rerank_input_count > 0 and record.rerank_output_count == 0:
            issues.append("重排输出为 0")
            suggestions.append("检查 reranker 模型是否正常加载")

        # 检查最终结果
        if record.final_evidence_count == 0:
            issues.append("最终证据数为 0，综述该章节会为空")
            suggestions.append("触发证据不足 fallback，或手动补充文献")
        elif record.final_evidence_count < 3:
            issues.append(f"最终证据数过少：{record.final_evidence_count}")
            suggestions.append("考虑降低检索阈值，或使用更宽泛的查询词")

        # 检查耗时
        if record.timing.total > 30000:  # 超过 30 秒
            issues.append(f"检索总耗时过长：{record.timing.total:.0f}ms")
            if record.timing.rerank > 10000:
                issues.append(f"重排耗时过长：{record.timing.rerank:.0f}ms")
                suggestions.append("考虑减少重排输入数量，或使用更快的 reranker 模型")

        # 检查摘要库搜索错误
        if record.abstract_search_error:
            issues.append(f"摘要库搜索错误：{record.abstract_search_error}")
            suggestions.append("检查 FTS5 表结构和查询语法")

        # 判定状态
        if not issues:
            status = "good"
        elif len(issues) <= 2:
            status = "warning"
        else:
            status = "critical"

        summary = (
            f"查询: {record.original_query[:50]}... | "
            f"召回: {record.hybrid_recall_count} | "
            f"重排: {record.rerank_input_count}→{record.rerank_output_count} | "
            f"最终证据: {record.final_evidence_count} | "
            f"耗时: {record.timing.total:.0f}ms"
        )

        return {
            "status": status,
            "issues": issues,
            "suggestions": suggestions,
            "summary": summary,
            "record": record.to_dict(),
        }

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _save_record(self, record: RetrievalRecord):
        """保存单条记录到磁盘"""
        try:
            record_file = self.storage_dir / f"{record.record_id}.json"
            with open(record_file, "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存检索记录失败: {e}")

    def _delete_record_file(self, record_id: str):
        """删除单条记录文件"""
        try:
            record_file = self.storage_dir / f"{record_id}.json"
            if record_file.is_file():
                record_file.unlink()
        except Exception as e:
            print(f"⚠️  删除检索记录失败: {e}")

    def _load_index(self) -> list[dict]:
        """加载索引文件"""
        if self._index_file.is_file():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_index(self):
        """保存索引文件"""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存检索索引失败: {e}")

    def clear(self):
        """清空所有记录（慎用）"""
        with self._lock:
            self._cache.clear()
            self._index.clear()
            # 删除所有记录文件
            for f in self.storage_dir.glob("*.json"):
                if f.name != "index.json":
                    f.unlink()
            self._save_index()


# =============================================================================
# 全局单例（方便使用）
# =============================================================================

_observability_instance: Optional[RetrievalObservability] = None
_observability_lock = threading.Lock()


def get_observability() -> RetrievalObservability:
    """获取全局检索可观测性单例"""
    global _observability_instance
    if _observability_instance is None:
        with _observability_lock:
            if _observability_instance is None:
                _observability_instance = RetrievalObservability()
    return _observability_instance
