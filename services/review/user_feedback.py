"""
Sci-Pal 用户反馈闭环模块 V33.6

用途：记录用户对生成结果的修改，形成反馈闭环，用于后续微调 reranker/prompt。
- 记录：用户修改的原文 vs 编辑后文本、修改类型、修改位置
- 查询：按 review_id / paper_id / section_id / 反馈类型查询
- 统计：反馈数量、修改类型分布、高频修改词
- 应用：用于微调 reranker 权重、优化 prompt、改进检索策略

设计原则：
- 完整记录：original 和 edited 都保存，支持 diff 对比
- 可追溯：每条反馈都有唯一 ID、时间戳、操作者
- 可分析：提供统计接口，方便发现系统薄弱环节
- 隐私保护：用户反馈数据本地存储，不上传
"""

import json
import time
import uuid
import threading
import difflib
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict


# =============================================================================
# 数据结构
# =============================================================================

class FeedbackType(str, Enum):
    """反馈类型"""
    CONTENT_EDIT = "content_edit"          # 内容修改（改写句子/段落）
    CITATION_FIX = "citation_fix"          # 引用修正（修改引用标记/添加/删除引用）
    SECTION_ADD = "section_add"            # 章节新增
    SECTION_DELETE = "section_delete"      # 章节删除
    SECTION_REORDER = "section_reorder"    # 章节重排
    EVIDENCE_ADD = "evidence_add"          # 证据添加（手动添加证据卡片）
    EVIDENCE_REMOVE = "evidence_remove"    # 证据移除
    EVIDENCE_REASSIGN = "evidence_reassign"  # 证据重新分配到其他章节
    RATING = "rating"                       # 评分（好/中/差）
    COMMENT = "comment"                     # 文字评论/备注
    OTHER = "other"                         # 其他

    @property
    def label_zh(self) -> str:
        """中文标签"""
        return {
            "content_edit": "内容修改",
            "citation_fix": "引用修正",
            "section_add": "章节新增",
            "section_delete": "章节删除",
            "section_reorder": "章节重排",
            "evidence_add": "证据添加",
            "evidence_remove": "证据移除",
            "evidence_reassign": "证据重新分配",
            "rating": "评分",
            "comment": "文字评论",
            "other": "其他",
        }[self.value]


class FeedbackRating(str, Enum):
    """反馈评分"""
    EXCELLENT = "excellent"  # 优秀
    GOOD = "good"            # 良好
    FAIR = "fair"            # 一般
    POOR = "poor"            # 较差
    BAD = "bad"              # 很差

    @property
    def score(self) -> int:
        """数值分数（1-5）"""
        return {
            "excellent": 5,
            "good": 4,
            "fair": 3,
            "poor": 2,
            "bad": 1,
        }[self.value]


@dataclass
class TextDiff:
    """文本差异记录"""
    original: str = ""
    edited: str = ""
    diff_html: str = ""  # HTML 格式的 diff（可选）
    changed_chars: int = 0  # 变更字符数
    changed_ratio: float = 0.0  # 变更比例（0-1）


@dataclass
class UserFeedback:
    """用户反馈记录"""
    # 基本信息
    feedback_id: str = field(default_factory=lambda: f"fb_{uuid.uuid4().hex[:12]}")
    review_id: str = ""
    task_id: str = ""
    section_id: str = ""
    paper_id: str = ""
    evidence_id: str = ""

    # 反馈信息
    feedback_type: str = FeedbackType.OTHER.value
    rating: str = ""  # 如果是评分类型
    comment: str = ""  # 用户文字评论

    # 文本差异（如果是内容修改）
    text_diff: Optional[TextDiff] = None

    # 元数据
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    timestamp_unix: float = field(default_factory=time.time)
    user_id: str = "default_user"
    session_id: str = ""
    source: str = "frontend"  # 反馈来源：frontend / api / manual

    # 处理状态
    processed: bool = False  # 是否已被用于微调/优化
    processed_at: str = ""
    processing_notes: str = ""

    # 附加信息
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.text_diff:
            d["text_diff"] = asdict(self.text_diff)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "UserFeedback":
        if "text_diff" in d and d["text_diff"]:
            d["text_diff"] = TextDiff(**d["text_diff"])
        return cls(**d)


@dataclass
class FeedbackStats:
    """反馈统计信息"""
    total_feedback: int = 0
    time_range_start: str = ""
    time_range_end: str = ""

    # 按类型统计
    by_type: dict[str, int] = field(default_factory=dict)

    # 评分统计
    avg_rating: float = 0.0
    rating_distribution: dict[str, int] = field(default_factory=dict)

    # 内容修改统计
    total_content_edits: int = 0
    avg_changed_ratio: float = 0.0

    # 引用修正统计
    total_citation_fixes: int = 0

    # 处理状态
    processed_count: int = 0
    unprocessed_count: int = 0

    # 高频修改的章节/论文
    top_sections: list[tuple[str, int]] = field(default_factory=list)
    top_papers: list[tuple[str, int]] = field(default_factory=list)


# =============================================================================
# 用户反馈管理器
# =============================================================================

class UserFeedbackManager:
    """
    用户反馈管理器

    用法：
        manager = UserFeedbackManager()

        # 记录内容修改
        feedback = manager.record_content_edit(
            review_id="rev_001",
            section_id="sec_001",
            original="STAT1 is important for immunity.",
            edited="STAT1 plays a critical role in antiviral immunity.",
            user_id="user_001",
        )

        # 记录评分
        manager.record_rating(
            review_id="rev_001",
            rating="good",
            comment="整体不错，但第二章需要更多证据",
        )

        # 记录引用修正
        manager.record_citation_fix(
            review_id="rev_001",
            section_id="sec_001",
            original="[1]",
            edited="[1][2]",
            comment="补充了第二篇引用",
        )

        # 查询反馈
        feedbacks = manager.get_by_review_id("rev_001")
        stats = manager.get_stats(last_n=100)
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_records: int = 10000,
    ):
        """
        Args:
            storage_dir: 存储目录，默认 data/user_feedback/
            max_records: 最多保留的反馈记录数
        """
        self.max_records = max_records
        self._lock = threading.Lock()
        self._cache: dict[str, UserFeedback] = {}

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "user_feedback"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 索引文件
        self._index_file = self.storage_dir / "index.json"
        self._index: list[dict] = self._load_index()

    # -------------------------------------------------------------------------
    # 记录反馈
    # -------------------------------------------------------------------------

    def record_feedback(self, feedback: UserFeedback) -> str:
        """记录一条用户反馈（通用接口）"""
        with self._lock:
            self._cache[feedback.feedback_id] = feedback

            # 更新索引
            self._index.append({
                "feedback_id": feedback.feedback_id,
                "review_id": feedback.review_id,
                "section_id": feedback.section_id,
                "paper_id": feedback.paper_id,
                "feedback_type": feedback.feedback_type,
                "rating": feedback.rating,
                "timestamp": feedback.timestamp,
                "timestamp_unix": feedback.timestamp_unix,
                "processed": feedback.processed,
            })

            # 限制索引大小
            if len(self._index) > self.max_records:
                old_records = self._index[:-self.max_records]
                for old in old_records:
                    self._delete_feedback_file(old["feedback_id"])
                    self._cache.pop(old["feedback_id"], None)
                self._index = self._index[-self.max_records:]

            self._save_index()

        self._save_feedback(feedback)
        return feedback.feedback_id

    def record_content_edit(
        self,
        review_id: str,
        section_id: str,
        original: str,
        edited: str,
        user_id: str = "default_user",
        comment: str = "",
    ) -> UserFeedback:
        """记录内容修改"""
        # 计算 diff
        diff = self._compute_text_diff(original, edited)

        feedback = UserFeedback(
            review_id=review_id,
            section_id=section_id,
            feedback_type=FeedbackType.CONTENT_EDIT.value,
            text_diff=diff,
            user_id=user_id,
            comment=comment,
        )
        self.record_feedback(feedback)
        return feedback

    def record_citation_fix(
        self,
        review_id: str,
        section_id: str,
        original: str,
        edited: str,
        user_id: str = "default_user",
        comment: str = "",
    ) -> UserFeedback:
        """记录引用修正"""
        diff = self._compute_text_diff(original, edited)

        feedback = UserFeedback(
            review_id=review_id,
            section_id=section_id,
            feedback_type=FeedbackType.CITATION_FIX.value,
            text_diff=diff,
            user_id=user_id,
            comment=comment,
        )
        self.record_feedback(feedback)
        return feedback

    def record_rating(
        self,
        review_id: str,
        rating: str,
        comment: str = "",
        user_id: str = "default_user",
        section_id: str = "",
    ) -> UserFeedback:
        """记录评分"""
        feedback = UserFeedback(
            review_id=review_id,
            section_id=section_id,
            feedback_type=FeedbackType.RATING.value,
            rating=rating,
            comment=comment,
            user_id=user_id,
        )
        self.record_feedback(feedback)
        return feedback

    def record_comment(
        self,
        review_id: str,
        comment: str,
        section_id: str = "",
        user_id: str = "default_user",
    ) -> UserFeedback:
        """记录文字评论"""
        feedback = UserFeedback(
            review_id=review_id,
            section_id=section_id,
            feedback_type=FeedbackType.COMMENT.value,
            comment=comment,
            user_id=user_id,
        )
        self.record_feedback(feedback)
        return feedback

    def record_evidence_change(
        self,
        review_id: str,
        section_id: str,
        evidence_id: str,
        change_type: str,  # add / remove / reassign
        user_id: str = "default_user",
        comment: str = "",
    ) -> UserFeedback:
        """记录证据变更"""
        if change_type == "add":
            fb_type = FeedbackType.EVIDENCE_ADD.value
        elif change_type == "remove":
            fb_type = FeedbackType.EVIDENCE_REMOVE.value
        else:
            fb_type = FeedbackType.EVIDENCE_REASSIGN.value

        feedback = UserFeedback(
            review_id=review_id,
            section_id=section_id,
            evidence_id=evidence_id,
            feedback_type=fb_type,
            comment=comment,
            user_id=user_id,
        )
        self.record_feedback(feedback)
        return feedback

    # -------------------------------------------------------------------------
    # 查询反馈
    # -------------------------------------------------------------------------

    def get_feedback(self, feedback_id: str) -> Optional[UserFeedback]:
        """按 ID 查询单条反馈"""
        with self._lock:
            if feedback_id in self._cache:
                return self._cache[feedback_id]

        feedback_file = self.storage_dir / f"{feedback_id}.json"
        if feedback_file.is_file():
            try:
                with open(feedback_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                feedback = UserFeedback.from_dict(data)
                with self._lock:
                    self._cache[feedback_id] = feedback
                return feedback
            except Exception as e:
                print(f"⚠️  读取用户反馈失败 {feedback_id}: {e}")
        return None

    def get_by_review_id(self, review_id: str) -> list[UserFeedback]:
        """按综述 ID 查询所有反馈"""
        # 先在锁内获取 feedback_id 列表，避免死锁
        with self._lock:
            feedback_ids = [idx["feedback_id"] for idx in self._index if idx.get("review_id") == review_id]
        # 释放锁后再逐个加载
        results = []
        for fid in feedback_ids:
            feedback = self.get_feedback(fid)
            if feedback:
                results.append(feedback)
        results.sort(key=lambda f: f.timestamp_unix)
        return results

    def get_by_section_id(self, section_id: str) -> list[UserFeedback]:
        """按章节 ID 查询所有反馈"""
        with self._lock:
            feedback_ids = [idx["feedback_id"] for idx in self._index if idx.get("section_id") == section_id]
        results = []
        for fid in feedback_ids:
            feedback = self.get_feedback(fid)
            if feedback:
                results.append(feedback)
        results.sort(key=lambda f: f.timestamp_unix)
        return results

    def get_by_type(self, feedback_type: str) -> list[UserFeedback]:
        """按反馈类型查询"""
        with self._lock:
            feedback_ids = [idx["feedback_id"] for idx in self._index if idx.get("feedback_type") == feedback_type]
        results = []
        for fid in feedback_ids:
            feedback = self.get_feedback(fid)
            if feedback:
                results.append(feedback)
        results.sort(key=lambda f: f.timestamp_unix)
        return results

    def get_unprocessed(self, limit: int = 100) -> list[UserFeedback]:
        """获取未处理的反馈（用于微调/优化）"""
        with self._lock:
            feedback_ids = []
            for idx in reversed(self._index):
                if not idx.get("processed", False):
                    feedback_ids.append(idx["feedback_id"])
                    if len(feedback_ids) >= limit:
                        break
        results = []
        for fid in feedback_ids:
            feedback = self.get_feedback(fid)
            if feedback:
                results.append(feedback)
        return results

    def list_recent(self, n: int = 20) -> list[UserFeedback]:
        """列出最近的 N 条反馈"""
        with self._lock:
            recent_idx = self._index[-n:] if len(self._index) > n else self._index[:]
        results = []
        for idx in reversed(recent_idx):
            feedback = self.get_feedback(idx["feedback_id"])
            if feedback:
                results.append(feedback)
        return results

    # -------------------------------------------------------------------------
    # 统计分析
    # -------------------------------------------------------------------------

    def get_stats(self, last_n: int = 1000) -> FeedbackStats:
        """获取反馈统计信息"""
        recent = self.list_recent(last_n)
        if not recent:
            return FeedbackStats()

        stats = FeedbackStats(
            total_feedback=len(recent),
            time_range_start=recent[-1].timestamp if recent else "",
            time_range_end=recent[0].timestamp if recent else "",
        )

        # 按类型统计
        by_type = defaultdict(int)
        for f in recent:
            by_type[f.feedback_type] += 1
        stats.by_type = dict(sorted(by_type.items(), key=lambda x: -x[1]))

        # 评分统计
        ratings = [f.rating for f in recent if f.rating]
        if ratings:
            try:
                stats.avg_rating = sum(FeedbackRating(r).score for r in ratings) / len(ratings)
            except Exception:
                pass
            rating_dist = defaultdict(int)
            for r in ratings:
                rating_dist[r] += 1
            stats.rating_distribution = dict(rating_dist)

        # 内容修改统计
        content_edits = [f for f in recent if f.feedback_type == FeedbackType.CONTENT_EDIT.value]
        stats.total_content_edits = len(content_edits)
        if content_edits:
            ratios = [f.text_diff.changed_ratio for f in content_edits if f.text_diff]
            if ratios:
                stats.avg_changed_ratio = sum(ratios) / len(ratios)

        # 引用修正统计
        stats.total_citation_fixes = sum(
            1 for f in recent if f.feedback_type == FeedbackType.CITATION_FIX.value
        )

        # 处理状态
        stats.processed_count = sum(1 for f in recent if f.processed)
        stats.unprocessed_count = len(recent) - stats.processed_count

        # 高频修改的章节/论文
        section_counts = defaultdict(int)
        paper_counts = defaultdict(int)
        for f in recent:
            if f.section_id:
                section_counts[f.section_id] += 1
            if f.paper_id:
                paper_counts[f.paper_id] += 1
        stats.top_sections = sorted(section_counts.items(), key=lambda x: -x[1])[:10]
        stats.top_papers = sorted(paper_counts.items(), key=lambda x: -x[1])[:10]

        return stats

    def get_improvement_suggestions(self) -> list[dict]:
        """
        基于反馈数据生成系统改进建议

        返回：
        建议列表，每个建议包含：area（改进领域）、issue（问题描述）、
        evidence（证据/数据）、suggestion（具体建议）、priority（优先级）
        """
        stats = self.get_stats(last_n=500)
        suggestions = []

        # 1. 检查评分是否偏低
        if stats.avg_rating > 0 and stats.avg_rating < 3.0:
            suggestions.append({
                "area": "生成质量",
                "issue": f"平均评分偏低（{stats.avg_rating:.1f}/5）",
                "evidence": f"共 {stats.rating_distribution.get('poor', 0) + stats.rating_distribution.get('bad', 0)} 条差评",
                "suggestion": "优化 prompt，增加证据约束，降低无依据推测",
                "priority": "high",
            })

        # 2. 检查内容修改比例是否过高
        if stats.avg_changed_ratio > 0.3:
            suggestions.append({
                "area": "内容生成",
                "issue": f"内容修改比例过高（平均 {stats.avg_changed_ratio:.1%}）",
                "evidence": f"共 {stats.total_content_edits} 次内容修改",
                "suggestion": "分析高频修改的章节，优化该章节的检索策略和写作 prompt",
                "priority": "high",
            })

        # 3. 检查引用修正是否频繁
        if stats.total_citation_fixes > stats.total_feedback * 0.1:
            suggestions.append({
                "area": "引用准确性",
                "issue": "引用修正频繁（超过 10% 的反馈是引用修正）",
                "evidence": f"共 {stats.total_citation_fixes} 次引用修正",
                "suggestion": "加强引用校验，生成后自动检查引用标记是否正确",
                "priority": "medium",
            })

        # 4. 检查高频修改的章节
        if stats.top_sections and stats.top_sections[0][1] > 5:
            top_section = stats.top_sections[0]
            suggestions.append({
                "area": "章节优化",
                "issue": f"章节 {top_section[0]} 被频繁修改（{top_section[1]} 次）",
                "evidence": f"Top 10 高频修改章节: {[s[0] for s in stats.top_sections[:5]]}",
                "suggestion": "重点优化该章节的检索关键词和写作 prompt",
                "priority": "medium",
            })

        # 5. 检查未处理反馈积压
        if stats.unprocessed_count > 100:
            suggestions.append({
                "area": "反馈处理",
                "issue": f"未处理反馈积压（{stats.unprocessed_count} 条）",
                "evidence": f"已处理 {stats.processed_count} 条，未处理 {stats.unprocessed_count} 条",
                "suggestion": "定期处理用户反馈，用于微调 reranker 和优化 prompt",
                "priority": "low",
            })

        return suggestions

    # -------------------------------------------------------------------------
    # 反馈处理（用于微调）
    # -------------------------------------------------------------------------

    def mark_processed(
        self,
        feedback_id: str,
        notes: str = "",
    ) -> bool:
        """标记反馈为已处理（已用于微调/优化）"""
        feedback = self.get_feedback(feedback_id)
        if not feedback:
            return False

        feedback.processed = True
        feedback.processed_at = datetime.now().isoformat()
        feedback.processing_notes = notes

        # 更新索引
        with self._lock:
            for idx in self._index:
                if idx["feedback_id"] == feedback_id:
                    idx["processed"] = True
                    break
            self._save_index()

        self._save_feedback(feedback)
        return True

    def mark_batch_processed(
        self,
        feedback_ids: list[str],
        notes: str = "",
    ) -> int:
        """批量标记为已处理，返回成功数量"""
        count = 0
        for fid in feedback_ids:
            if self.mark_processed(fid, notes):
                count += 1
        return count

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _compute_text_diff(self, original: str, edited: str) -> TextDiff:
        """计算文本差异"""
        # 计算变更字符数
        changed_chars = abs(len(edited) - len(original))
        total_chars = max(len(original), len(edited), 1)
        changed_ratio = min(changed_chars / total_chars, 1.0)

        # 生成 HTML diff（可选，简单实现）
        try:
            diff = difflib.HtmlDiff()
            diff_html = diff.make_file(
                original.splitlines(),
                edited.splitlines(),
                fromdesc="Original",
                todesc="Edited",
                context=True,
            )
        except Exception:
            diff_html = ""

        return TextDiff(
            original=original,
            edited=edited,
            diff_html=diff_html,
            changed_chars=changed_chars,
            changed_ratio=changed_ratio,
        )

    def _save_feedback(self, feedback: UserFeedback):
        """保存单条反馈到磁盘"""
        try:
            feedback_file = self.storage_dir / f"{feedback.feedback_id}.json"
            with open(feedback_file, "w", encoding="utf-8") as f:
                json.dump(feedback.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存用户反馈失败: {e}")

    def _delete_feedback_file(self, feedback_id: str):
        """删除单条反馈文件"""
        try:
            feedback_file = self.storage_dir / f"{feedback_id}.json"
            if feedback_file.is_file():
                feedback_file.unlink()
        except Exception as e:
            print(f"⚠️  删除用户反馈失败: {e}")

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
            print(f"⚠️  保存用户反馈索引失败: {e}")

    def clear(self):
        """清空所有反馈（慎用）"""
        with self._lock:
            self._cache.clear()
            self._index.clear()
            for f in self.storage_dir.glob("*.json"):
                if f.name != "index.json":
                    f.unlink()
            self._save_index()


# =============================================================================
# 全局单例
# =============================================================================

_feedback_manager_instance: Optional[UserFeedbackManager] = None
_feedback_manager_lock = threading.Lock()


def get_feedback_manager() -> UserFeedbackManager:
    """获取全局用户反馈管理器单例"""
    global _feedback_manager_instance
    if _feedback_manager_instance is None:
        with _feedback_manager_lock:
            if _feedback_manager_instance is None:
                _feedback_manager_instance = UserFeedbackManager()
    return _feedback_manager_instance
