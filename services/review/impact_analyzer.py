"""
Sci-Pal 影响范围评估与局部重算模块 V33.6

用途：当 EvidenceCard 或数据源变更时，评估受影响的章节和综述，支持局部重算。
- 影响评估：自动识别受影响的章节、段落、综述
- 局部重算：只重算受影响的部分，不全局重跑
- 变更报告：提供受影响范围、建议操作、预估重算时间
- 依赖追踪：维护 EvidenceCard → 章节 → 综述的依赖关系图

设计原则：
- 最小影响：只重算真正受影响的部分，不浪费计算资源
- 可追溯：每次变更都有完整的影响范围记录
- 可配置：重算策略可配置（自动/手动/阈值触发）
- 增量优先：优先使用增量更新，避免全量重建
"""

import json
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


# =============================================================================
# 数据结构
# =============================================================================

class ChangeType(str, Enum):
    """变更类型"""
    EVIDENCE_ADD = "evidence_add"          # 新增证据
    EVIDENCE_REMOVE = "evidence_remove"    # 移除证据
    EVIDENCE_UPDATE = "evidence_update"    # 更新证据
    EVIDENCE_MERGE = "evidence_merge"      # 合并证据
    EVIDENCE_DEPRECATE = "evidence_deprecate"  # 证据失效
    EVIDENCE_CONFLICT = "evidence_conflict"    # 证据冲突
    PAPER_ADD = "paper_add"                # 新增论文
    PAPER_REMOVE = "paper_remove"          # 移除论文
    OUTLINE_CHANGE = "outline_change"      # 大纲变更
    DATA_SYNC = "data_sync"                # 数据同步


class ImpactLevel(str, Enum):
    """影响级别"""
    NONE = "none"          # 无影响
    LOW = "low"            # 低影响（只影响少量段落）
    MEDIUM = "medium"      # 中等影响（影响整个章节）
    HIGH = "high"          # 高影响（影响多个章节）
    CRITICAL = "critical"  # 严重影响（影响整篇综述，建议全量重算）


class RecalcStrategy(str, Enum):
    """重算策略"""
    AUTO = "auto"          # 自动重算（影响达到阈值时自动触发）
    MANUAL = "manual"      # 手动重算（用户确认后重算）
    THRESHOLD = "threshold"  # 阈值触发（影响超过阈值时提示用户）
    NONE = "none"          # 不重算（只记录影响）


@dataclass
class ImpactedSection:
    """受影响的章节"""
    section_id: str = ""
    section_title: str = ""
    chapter_id: str = ""
    chapter_title: str = ""

    # 影响详情
    impact_level: str = ImpactLevel.LOW.value
    affected_evidence_count: int = 0
    affected_evidence_ids: list[str] = field(default_factory=list)

    # 重算建议
    should_recalc: bool = False
    recalc_reason: str = ""
    estimated_recalc_seconds: float = 0.0

    # 当前状态
    current_status: str = "pending"  # pending / recalculating / completed / skipped


@dataclass
class ImpactReport:
    """影响范围评估报告"""
    report_id: str = field(default_factory=lambda: f"impact_{uuid.uuid4().hex[:12]}")
    change_type: str = ""
    change_description: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # 影响范围
    total_impacted_reviews: int = 0
    total_impacted_chapters: int = 0
    total_impacted_sections: int = 0
    total_impacted_evidence: int = 0
    overall_impact_level: str = ImpactLevel.NONE.value

    # 受影响的章节详情
    impacted_sections: list[ImpactedSection] = field(default_factory=list)

    # 受影响的综述
    impacted_review_ids: list[str] = field(default_factory=list)

    # 重算建议
    recalc_strategy: str = RecalcStrategy.MANUAL.value
    should_recalc: bool = False
    recalc_scope: str = ""  # partial / full
    estimated_total_recalc_seconds: float = 0.0
    recommendations: list[str] = field(default_factory=list)

    # 处理状态
    status: str = "pending"  # pending / in_progress / completed / dismissed
    processed_at: str = ""
    processing_notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["impacted_sections"] = [asdict(s) for s in self.impacted_sections]
        return d


@dataclass
class DependencyGraph:
    """依赖关系图（EvidenceCard → 章节 → 综述）"""
    # evidence_id -> set of section_ids
    evidence_to_sections: dict[str, set[str]] = field(default_factory=dict)
    # section_id -> set of evidence_ids
    section_to_evidence: dict[str, set[str]] = field(default_factory=dict)
    # section_id -> review_id
    section_to_review: dict[str, str] = field(default_factory=dict)
    # review_id -> set of section_ids
    review_to_sections: dict[str, set[str]] = field(default_factory=dict)
    # paper_id -> set of evidence_ids
    paper_to_evidence: dict[str, set[str]] = field(default_factory=dict)


# =============================================================================
# 影响分析器
# =============================================================================

class ImpactAnalyzer:
    """
    影响范围评估与局部重算分析器

    用法：
        analyzer = ImpactAnalyzer()

        # 注册依赖关系（从大纲和证据分配中提取）
        analyzer.register_dependency(
            evidence_id='ev_001',
            section_id='sec_001',
            review_id='rev_001',
            paper_id='paper_001',
        )

        # 评估变更影响
        report = analyzer.assess_impact(
            change_type='evidence_add',
            change_description='新增 STAT1 相关证据',
            evidence_ids=['ev_new_001'],
            paper_ids=['paper_new_001'],
        )

        # 获取受影响的章节
        sections = report.impacted_sections

        # 标记重算完成
        analyzer.mark_recalc_completed(report.report_id)
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_reports: int = 500,
        auto_recalc_threshold: str = ImpactLevel.MEDIUM.value,
    ):
        """
        Args:
            storage_dir: 存储目录，默认 data/impact_analyzer/
            max_reports: 最多保留的报告数
            auto_recalc_threshold: 自动重算阈值（影响达到此级别时建议重算）
        """
        self.max_reports = max_reports
        self.auto_recalc_threshold = auto_recalc_threshold
        self._lock = threading.Lock()

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "impact_analyzer"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 报告目录
        self._reports_dir = self.storage_dir / "reports"
        self._reports_dir.mkdir(exist_ok=True)

        # 依赖图
        self._dep_graph = DependencyGraph()
        self._dep_graph_file = self.storage_dir / "dependency_graph.json"
        self._load_dependency_graph()

        # 报告索引
        self._reports_index_file = self.storage_dir / "reports_index.json"
        self._reports_index: list[dict] = self._load_json(self._reports_index_file, [])

    # -------------------------------------------------------------------------
    # 依赖关系管理
    # -------------------------------------------------------------------------

    def register_dependency(
        self,
        evidence_id: str,
        section_id: str,
        review_id: str,
        paper_id: str = "",
        section_title: str = "",
        chapter_id: str = "",
        chapter_title: str = "",
    ):
        """注册依赖关系（EvidenceCard → 章节 → 综述）"""
        with self._lock:
            # evidence → sections
            if evidence_id not in self._dep_graph.evidence_to_sections:
                self._dep_graph.evidence_to_sections[evidence_id] = set()
            self._dep_graph.evidence_to_sections[evidence_id].add(section_id)

            # section → evidence
            if section_id not in self._dep_graph.section_to_evidence:
                self._dep_graph.section_to_evidence[section_id] = set()
            self._dep_graph.section_to_evidence[section_id].add(evidence_id)

            # section → review
            self._dep_graph.section_to_review[section_id] = review_id

            # review → sections
            if review_id not in self._dep_graph.review_to_sections:
                self._dep_graph.review_to_sections[review_id] = set()
            self._dep_graph.review_to_sections[review_id].add(section_id)

            # paper → evidence
            if paper_id:
                if paper_id not in self._dep_graph.paper_to_evidence:
                    self._dep_graph.paper_to_evidence[paper_id] = set()
                self._dep_graph.paper_to_evidence[paper_id].add(evidence_id)

            # 保存章节元数据
            self._section_metadata[section_id] = {
                "section_title": section_title,
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
            }

            self._save_dependency_graph()

    def unregister_dependency(self, evidence_id: str, section_id: str = ""):
        """注销依赖关系"""
        with self._lock:
            if section_id:
                # 只移除特定章节的依赖
                if evidence_id in self._dep_graph.evidence_to_sections:
                    self._dep_graph.evidence_to_sections[evidence_id].discard(section_id)
                if section_id in self._dep_graph.section_to_evidence:
                    self._dep_graph.section_to_evidence[section_id].discard(evidence_id)
            else:
                # 移除该证据的所有依赖
                sections = self._dep_graph.evidence_to_sections.get(evidence_id, set())
                for sec in sections:
                    if sec in self._dep_graph.section_to_evidence:
                        self._dep_graph.section_to_evidence[sec].discard(evidence_id)
                self._dep_graph.evidence_to_sections.pop(evidence_id, None)

            self._save_dependency_graph()

    # 章节元数据存储
    _section_metadata: dict[str, dict] = {}

    # -------------------------------------------------------------------------
    # 影响评估
    # -------------------------------------------------------------------------

    def assess_impact(
        self,
        change_type: str,
        change_description: str = "",
        evidence_ids: list[str] = None,
        paper_ids: list[str] = None,
        section_ids: list[str] = None,
        review_ids: list[str] = None,
    ) -> ImpactReport:
        """
        评估变更的影响范围

        Args:
            change_type: 变更类型
            change_description: 变更描述
            evidence_ids: 受影响的证据 ID 列表
            paper_ids: 受影响的论文 ID 列表
            section_ids: 受影响的章节 ID 列表
            review_ids: 受影响的综述 ID 列表

        Returns:
            影响范围评估报告
        """
        report = ImpactReport(
            change_type=change_type,
            change_description=change_description,
        )

        # 收集所有受影响的章节
        impacted_section_ids = set()

        with self._lock:
            # 通过证据 ID 找章节
            if evidence_ids:
                for eid in evidence_ids:
                    sections = self._dep_graph.evidence_to_sections.get(eid, set())
                    impacted_section_ids.update(sections)
                report.total_impacted_evidence = len(evidence_ids)

            # 通过论文 ID 找证据，再找章节
            if paper_ids:
                for pid in paper_ids:
                    ev_ids = self._dep_graph.paper_to_evidence.get(pid, set())
                    for eid in ev_ids:
                        sections = self._dep_graph.evidence_to_sections.get(eid, set())
                        impacted_section_ids.update(sections)
                        report.total_impacted_evidence += 1

            # 直接指定章节
            if section_ids:
                impacted_section_ids.update(section_ids)

            # 直接指定综述（影响综述下所有章节）
            if review_ids:
                for rid in review_ids:
                    sections = self._dep_graph.review_to_sections.get(rid, set())
                    impacted_section_ids.update(sections)

        # 构建受影响章节详情
        impacted_reviews = set()
        impacted_chapters = set()

        for sec_id in impacted_section_ids:
            meta = self._section_metadata.get(sec_id, {})
            review_id = self._dep_graph.section_to_review.get(sec_id, "")
            if review_id:
                impacted_reviews.add(review_id)

            chapter_id = meta.get("chapter_id", "")
            if chapter_id:
                impacted_chapters.add(chapter_id)

            # 计算该章节受影响的证据数
            section_ev_ids = self._dep_graph.section_to_evidence.get(sec_id, set())
            affected_ev_ids = []
            if evidence_ids:
                affected_ev_ids = [eid for eid in evidence_ids if eid in section_ev_ids]

            # 评估影响级别
            impact_level = self._calculate_section_impact_level(
                len(section_ev_ids), len(affected_ev_ids), change_type
            )

            # 估算重算时间（假设每个段落约 2 秒）
            estimated_seconds = len(affected_ev_ids) * 2.0 if affected_ev_ids else 5.0

            section = ImpactedSection(
                section_id=sec_id,
                section_title=meta.get("section_title", sec_id),
                chapter_id=chapter_id,
                chapter_title=meta.get("chapter_title", ""),
                impact_level=impact_level,
                affected_evidence_count=len(affected_ev_ids),
                affected_evidence_ids=affected_ev_ids,
                should_recalc=impact_level in [ImpactLevel.MEDIUM.value, ImpactLevel.HIGH.value, ImpactLevel.CRITICAL.value],
                recalc_reason=f"变更类型: {change_type}, 受影响证据: {len(affected_ev_ids)}",
                estimated_recalc_seconds=estimated_seconds,
            )
            report.impacted_sections.append(section)

        # 汇总统计
        report.total_impacted_sections = len(impacted_section_ids)
        report.total_impacted_chapters = len(impacted_chapters)
        report.total_impacted_reviews = len(impacted_reviews)
        report.impacted_review_ids = list(impacted_reviews)

        # 计算总体影响级别
        report.overall_impact_level = self._calculate_overall_impact_level(report)

        # 重算建议
        report.should_recalc = report.overall_impact_level in [
            ImpactLevel.MEDIUM.value, ImpactLevel.HIGH.value, ImpactLevel.CRITICAL.value
        ]
        report.recalc_scope = "full" if report.overall_impact_level == ImpactLevel.CRITICAL.value else "partial"
        report.estimated_total_recalc_seconds = sum(
            s.estimated_recalc_seconds for s in report.impacted_sections if s.should_recalc
        )

        # 生成建议
        report.recommendations = self._generate_recommendations(report)

        # 保存报告
        self._save_report(report)
        return report

    # -------------------------------------------------------------------------
    # 局部重算管理
    # -------------------------------------------------------------------------

    def mark_recalc_completed(
        self,
        report_id: str,
        recalculated_sections: list[str] = None,
        notes: str = "",
    ) -> bool:
        """标记重算完成"""
        report = self.get_report(report_id)
        if not report:
            return False

        report.status = "completed"
        report.processed_at = datetime.now().isoformat()
        report.processing_notes = notes

        # 更新章节状态
        if recalculated_sections:
            for sec in report.impacted_sections:
                if sec.section_id in recalculated_sections:
                    sec.current_status = "completed"

        self._save_report(report)
        return True

    def mark_recalc_skipped(self, report_id: str, reason: str = "") -> bool:
        """标记跳过重算"""
        report = self.get_report(report_id)
        if not report:
            return False

        report.status = "dismissed"
        report.processed_at = datetime.now().isoformat()
        report.processing_notes = reason
        self._save_report(report)
        return True

    def get_pending_reports(self, limit: int = 20) -> list[ImpactReport]:
        """获取待处理的影响报告"""
        with self._lock:
            report_ids = [
                idx["report_id"] for idx in reversed(self._reports_index)
                if idx.get("status") == "pending"
            ][:limit]

        results = []
        for rid in report_ids:
            report = self.get_report(rid)
            if report:
                results.append(report)
        return results

    # -------------------------------------------------------------------------
    # 查询
    # -------------------------------------------------------------------------

    def get_report(self, report_id: str) -> Optional[ImpactReport]:
        """获取影响报告"""
        report_file = self._reports_dir / f"{report_id}.json"
        if report_file.is_file():
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 恢复 impacted_sections
                sections = [ImpactedSection(**s) for s in data.pop("impacted_sections", [])]
                report = ImpactReport(**data)
                report.impacted_sections = sections
                return report
            except Exception as e:
                print(f"⚠️  读取影响报告失败 {report_id}: {e}")
        return None

    def list_reports(self, limit: int = 50) -> list[ImpactReport]:
        """列出影响报告"""
        with self._lock:
            report_ids = [idx["report_id"] for idx in reversed(self._reports_index)][:limit]

        results = []
        for rid in report_ids:
            report = self.get_report(rid)
            if report:
                results.append(report)
        return results

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _calculate_section_impact_level(
        self,
        total_evidence: int,
        affected_evidence: int,
        change_type: str,
    ) -> str:
        """计算章节影响级别"""
        if total_evidence == 0 or affected_evidence == 0:
            return ImpactLevel.NONE.value

        ratio = affected_evidence / total_evidence

        # 高影响变更类型
        high_impact_types = [ChangeType.EVIDENCE_REMOVE.value, ChangeType.EVIDENCE_DEPRECATE.value]
        if change_type in high_impact_types and ratio > 0.3:
            return ImpactLevel.HIGH.value

        if ratio >= 0.5:
            return ImpactLevel.HIGH.value
        elif ratio >= 0.2:
            return ImpactLevel.MEDIUM.value
        elif ratio >= 0.05:
            return ImpactLevel.LOW.value
        else:
            return ImpactLevel.NONE.value

    def _calculate_overall_impact_level(self, report: ImpactReport) -> str:
        """计算总体影响级别"""
        if not report.impacted_sections:
            return ImpactLevel.NONE.value

        levels = [s.impact_level for s in report.impacted_sections]

        if ImpactLevel.CRITICAL.value in levels or report.total_impacted_chapters >= 3:
            return ImpactLevel.CRITICAL.value
        if ImpactLevel.HIGH.value in levels:
            return ImpactLevel.HIGH.value
        if ImpactLevel.MEDIUM.value in levels:
            return ImpactLevel.MEDIUM.value
        if ImpactLevel.LOW.value in levels:
            return ImpactLevel.LOW.value
        return ImpactLevel.NONE.value

    def _generate_recommendations(self, report: ImpactReport) -> list[str]:
        """生成处理建议"""
        recommendations = []

        if report.overall_impact_level == ImpactLevel.NONE.value:
            recommendations.append("无显著影响，无需重算")
            return recommendations

        if report.should_recalc:
            if report.recalc_scope == "full":
                recommendations.append(f"建议全量重算（影响 {report.total_impacted_reviews} 篇综述，预估 {report.estimated_total_recalc_seconds:.0f} 秒）")
            else:
                sections_to_recalc = [s for s in report.impacted_sections if s.should_recalc]
                recommendations.append(f"建议局部重算 {len(sections_to_recalc)} 个章节（预估 {report.estimated_total_recalc_seconds:.0f} 秒）")

        # 针对不同变更类型的建议
        if report.change_type == ChangeType.EVIDENCE_CONFLICT.value:
            recommendations.append("存在证据冲突，建议人工复核后决定保留或替换")
        elif report.change_type == ChangeType.EVIDENCE_DEPRECATE.value:
            recommendations.append("已有证据失效，建议在受影响章节中替换为新证据")
        elif report.change_type == ChangeType.DATA_SYNC.value:
            recommendations.append("新数据已同步，建议评估是否需要更新综述")

        if report.total_impacted_reviews > 1:
            recommendations.append(f"影响多篇综述（{report.total_impacted_reviews} 篇），建议批量处理")

        return recommendations

    def _save_report(self, report: ImpactReport):
        """保存影响报告"""
        try:
            report_file = self._reports_dir / f"{report.report_id}.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

            with self._lock:
                # 检查是否已存在
                existing = next((i for i, idx in enumerate(self._reports_index) if idx["report_id"] == report.report_id), None)
                report_idx = {
                    "report_id": report.report_id,
                    "change_type": report.change_type,
                    "overall_impact_level": report.overall_impact_level,
                    "status": report.status,
                    "timestamp": report.timestamp,
                }
                if existing is not None:
                    self._reports_index[existing] = report_idx
                else:
                    self._reports_index.append(report_idx)

                # 限制报告数量
                if len(self._reports_index) > self.max_reports:
                    old_reports = self._reports_index[:-self.max_reports]
                    for old in old_reports:
                        report_file = self._reports_dir / f"{old['report_id']}.json"
                        if report_file.is_file():
                            report_file.unlink()
                    self._reports_index = self._reports_index[-self.max_reports:]

                self._save_json(self._reports_index_file, self._reports_index)
        except Exception as e:
            print(f"⚠️  保存影响报告失败: {e}")

    def _load_dependency_graph(self):
        """加载依赖图"""
        if self._dep_graph_file.is_file():
            try:
                with open(self._dep_graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._dep_graph.evidence_to_sections = {k: set(v) for k, v in data.get("evidence_to_sections", {}).items()}
                self._dep_graph.section_to_evidence = {k: set(v) for k, v in data.get("section_to_evidence", {}).items()}
                self._dep_graph.section_to_review = data.get("section_to_review", {})
                self._dep_graph.review_to_sections = {k: set(v) for k, v in data.get("review_to_sections", {}).items()}
                self._dep_graph.paper_to_evidence = {k: set(v) for k, v in data.get("paper_to_evidence", {}).items()}
                self._section_metadata = data.get("section_metadata", {})
            except Exception as e:
                print(f"⚠️  加载依赖图失败: {e}")

    def _save_dependency_graph(self):
        """保存依赖图"""
        try:
            data = {
                "evidence_to_sections": {k: list(v) for k, v in self._dep_graph.evidence_to_sections.items()},
                "section_to_evidence": {k: list(v) for k, v in self._dep_graph.section_to_evidence.items()},
                "section_to_review": self._dep_graph.section_to_review,
                "review_to_sections": {k: list(v) for k, v in self._dep_graph.review_to_sections.items()},
                "paper_to_evidence": {k: list(v) for k, v in self._dep_graph.paper_to_evidence.items()},
                "section_metadata": self._section_metadata,
            }
            with open(self._dep_graph_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存依赖图失败: {e}")

    def _load_json(self, file_path: Path, default):
        """加载 JSON 文件"""
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, file_path: Path, data):
        """保存 JSON 文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存 JSON 失败: {e}")


# =============================================================================
# 全局单例
# =============================================================================

_impact_analyzer_instance: Optional[ImpactAnalyzer] = None
_impact_analyzer_lock = threading.Lock()


def get_impact_analyzer() -> ImpactAnalyzer:
    """获取全局影响分析器单例"""
    global _impact_analyzer_instance
    if _impact_analyzer_instance is None:
        with _impact_analyzer_lock:
            if _impact_analyzer_instance is None:
                _impact_analyzer_instance = ImpactAnalyzer()
    return _impact_analyzer_instance
