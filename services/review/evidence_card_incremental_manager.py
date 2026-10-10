"""
Sci-Pal EvidenceCard 增量维护管理器 V33.5

用途：管理 EvidenceCard 的增量更新，让新论文"长进"已有结构，而不是简单堆进去。
核心操作：
1. append（追加）：把新证据追加到已有卡片（同一主题的补充证据）
2. create（创建）：创建新的 EvidenceCard
3. flag_conflict（标记冲突）：标记两个证据卡片之间存在冲突
4. deprecate（标记失效）：标记旧证据已被新证据取代
5. merge（合并）：合并相似的证据卡片

设计原则：
- 不重建，只追加 + 标记：旧数据不动，新数据挂上去
- 冲突用标记，不用删除：保留历史，可追溯
- EvidenceCard 是增量单位：不是论文，不是句子，而是 EvidenceCard
- 影响范围评估：只重算受影响的部分，不全局重跑
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

class CardOperationType(str, Enum):
    """卡片操作类型"""
    CREATE = "create"          # 创建新卡片
    APPEND = "append"          # 追加到已有卡片
    MERGE = "merge"            # 合并卡片
    DEPRECATE = "deprecate"    # 标记失效
    FLAG_CONFLICT = "flag_conflict"  # 标记冲突
    UPDATE = "update"          # 更新卡片内容
    RESTORE = "restore"        # 恢复已失效的卡片


class CardStatus(str, Enum):
    """卡片状态"""
    ACTIVE = "active"          # 活跃（正常使用）
    DEPRECATED = "deprecated"  # 已失效（被新证据取代）
    CONFLICT = "conflict"      # 存在冲突（需要人工/LLM 复核）
    MERGED = "merged"          # 已合并到其他卡片
    DRAFT = "draft"            # 草稿（待确认）


@dataclass
class CardVersion:
    """卡片版本记录"""
    version: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    operation: str = ""  # 操作类型
    operator: str = "system"  # 操作者（system / user / llm）
    reason: str = ""  # 操作原因
    changes: dict = field(default_factory=dict)  # 变更内容摘要


@dataclass
class ConflictRecord:
    """冲突记录"""
    conflict_id: str = field(default_factory=lambda: f"conflict_{uuid.uuid4().hex[:12]}")
    card_id_1: str = ""
    card_id_2: str = ""
    conflict_type: str = ""  # contradiction / inconsistency / outdated
    description: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved: bool = False
    resolution: str = ""  # 解决方案：keep_1 / keep_2 / merge / manual
    resolved_by: str = ""
    resolved_at: str = ""


@dataclass
class IncrementalOperationLog:
    """增量操作日志"""
    log_id: str = field(default_factory=lambda: f"op_{uuid.uuid4().hex[:12]}")
    operation: str = ""  # 操作类型
    card_id: str = ""  # 目标卡片
    related_card_ids: list[str] = field(default_factory=list)  # 相关卡片
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    operator: str = "system"
    reason: str = ""
    details: dict = field(default_factory=dict)
    affected_sections: list[str] = field(default_factory=list)  # 受影响的章节


# =============================================================================
# EvidenceCard 增量维护管理器
# =============================================================================

class EvidenceCardIncrementalManager:
    """
    EvidenceCard 增量维护管理器

    用法：
        manager = EvidenceCardIncrementalManager()

        # 创建新卡片
        card = manager.create_card(
            content="STAT1 is activated by JAK phosphorylation",
            paper_id="paper_001",
            para_id="para_001",
            section_id="section_001",
        )

        # 追加证据到已有卡片
        manager.append_evidence(
            card_id=card.evidence_id,
            new_content="STAT1 also responds to IFN-gamma",
            new_paper_id="paper_002",
        )

        # 标记冲突
        manager.flag_conflict(
            card_id_1="card_001",
            card_id_2="card_002",
            conflict_type="contradiction",
            description="STAT1 increases vs decreases immune response",
        )

        # 标记失效
        manager.deprecate_card(
            card_id="card_001",
            replaced_by="card_003",
            reason="New study with larger sample size",
        )

        # 合并卡片
        merged_card = manager.merge_cards(
            card_ids=["card_001", "card_002"],
            merge_strategy="concatenate",
        )
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_logs: int = 5000,
        relation_classifier=None,
    ):
        """
        Args:
            storage_dir: 存储目录，默认 data/evidence_incremental/
            max_logs: 最多保留的操作日志数
            relation_classifier: 句子关系判定器（可选，用于自动判定关系）
        """
        self.max_logs = max_logs
        self.relation_classifier = relation_classifier
        self._lock = threading.Lock()

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "evidence_incremental"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 内存中的卡片索引（evidence_id -> 卡片元数据）
        self._card_index: dict[str, dict] = {}

        # 操作日志
        self._operation_logs: list[IncrementalOperationLog] = []

        # 冲突记录
        self._conflicts: dict[str, ConflictRecord] = {}

        # 章节 -> 卡片ID 映射（用于影响范围评估）
        self._section_cards: dict[str, set[str]] = {}

        # 加载已有数据
        self._load_state()

    # -------------------------------------------------------------------------
    # 核心操作：创建
    # -------------------------------------------------------------------------

    def create_card(
        self,
        content: str,
        paper_id: str,
        para_id: str,
        section_id: str = "",
        evidence_type: str = "fact",
        original_quote: str = "",
        source_type: str = "full_text",
        match_method: str = "hybrid",
        rerank_score: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        创建新的 EvidenceCard

        Returns:
            卡片信息 dict（包含 evidence_id 等）
        """
        from .models import EvidenceCard

        evidence_id = f"ev_{paper_id}_{para_id}_{uuid.uuid4().hex[:8]}"

        card = EvidenceCard(
            evidence_id=evidence_id,
            content=content,
            evidence_type=evidence_type,
            original_quote=original_quote or content[:500],
            paper_id=paper_id,
            para_id=para_id,
            source_type=source_type,
            match_method=match_method,
            rerank_score=rerank_score,
            dedupe_key=f"{paper_id}_{para_id}",
        )

        # 保存卡片元数据到索引
        card_meta = {
            "evidence_id": evidence_id,
            "paper_id": paper_id,
            "para_id": para_id,
            "content_preview": content[:200],
            "status": CardStatus.ACTIVE.value,
            "section_id": section_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "versions": [CardVersion(operation="create", reason="Initial creation").__dict__],
            "replaced_by": "",
            "conflict_ids": [],
            "merged_from": [],
            "appended_evidence": [],  # 追加的证据列表
            "metadata": metadata or {},
        }

        with self._lock:
            self._card_index[evidence_id] = card_meta
            if section_id:
                if section_id not in self._section_cards:
                    self._section_cards[section_id] = set()
                self._section_cards[section_id].add(evidence_id)

        # 记录操作日志
        self._log_operation(
            operation=CardOperationType.CREATE.value,
            card_id=evidence_id,
            reason="创建新证据卡片",
            affected_sections=[section_id] if section_id else [],
            details={"paper_id": paper_id, "para_id": para_id},
        )

        self._save_state()
        return card_meta

    # -------------------------------------------------------------------------
    # 核心操作：追加
    # -------------------------------------------------------------------------

    def append_evidence(
        self,
        card_id: str,
        new_content: str,
        new_paper_id: str,
        new_para_id: str = "",
        reason: str = "",
    ) -> Optional[dict]:
        """
        把新证据追加到已有卡片（同一主题的补充证据）

        Args:
            card_id: 目标卡片 ID
            new_content: 新证据内容
            new_paper_id: 新证据所属论文
            new_para_id: 新证据所属段落
            reason: 追加原因

        Returns:
            更新后的卡片信息，失败返回 None
        """
        with self._lock:
            if card_id not in self._card_index:
                return None

            card = self._card_index[card_id]
            if card["status"] != CardStatus.ACTIVE.value:
                return None

            # 追加证据
            appended = {
                "content": new_content,
                "paper_id": new_paper_id,
                "para_id": new_para_id,
                "timestamp": datetime.now().isoformat(),
                "reason": reason,
            }
            card["appended_evidence"].append(appended)
            card["updated_at"] = datetime.now().isoformat()

            # 增加版本
            new_version = CardVersion(
                version=len(card["versions"]) + 1,
                operation="append",
                reason=reason or "追加补充证据",
                changes={"appended_paper": new_paper_id},
            )
            card["versions"].append(new_version.__dict__)

        # 记录操作日志
        affected = self._get_affected_sections(card_id)
        self._log_operation(
            operation=CardOperationType.APPEND.value,
            card_id=card_id,
            reason=reason or "追加补充证据",
            affected_sections=affected,
            details={"new_paper_id": new_paper_id},
        )

        self._save_state()
        return card

    # -------------------------------------------------------------------------
    # 核心操作：合并
    # -------------------------------------------------------------------------

    def merge_cards(
        self,
        card_ids: list[str],
        merge_strategy: str = "concatenate",
        reason: str = "",
    ) -> Optional[dict]:
        """
        合并多个相似的证据卡片

        Args:
            card_ids: 要合并的卡片 ID 列表
            merge_strategy: 合并策略
                - concatenate：拼接所有内容
                - keep_longest：保留最长的内容，其他作为追加
                - keep_highest_quality：保留质量最高的内容
            reason: 合并原因

        Returns:
            合并后的新卡片，失败返回 None
        """
        if len(card_ids) < 2:
            return None

        with self._lock:
            # 检查所有卡片都存在且活跃
            cards = []
            for cid in card_ids:
                if cid in self._card_index and self._card_index[cid]["status"] == CardStatus.ACTIVE.value:
                    cards.append(self._card_index[cid])

            if len(cards) < 2:
                return None

            # 按质量排序（如果有质量分）
            # 简单策略：按内容长度排序
            cards.sort(key=lambda c: len(c.get("content_preview", "")), reverse=True)

            # 合并内容
            if merge_strategy == "keep_longest":
                primary = cards[0]
                merged_content = primary["content_preview"]
                others = cards[1:]
            elif merge_strategy == "concatenate":
                primary = cards[0]
                contents = [c["content_preview"] for c in cards]
                merged_content = " ".join(contents)
                others = cards[1:]
            else:  # keep_highest_quality（默认同 keep_longest）
                primary = cards[0]
                merged_content = primary["content_preview"]
                others = cards[1:]

            # 创建合并后的新卡片
            merged_id = f"ev_merged_{uuid.uuid4().hex[:10]}"
            section_id = primary.get("section_id", "")

            merged_card = {
                "evidence_id": merged_id,
                "paper_id": primary["paper_id"],
                "para_id": primary["para_id"],
                "content_preview": merged_content[:500],
                "status": CardStatus.ACTIVE.value,
                "section_id": section_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "versions": [CardVersion(
                    operation="merge",
                    reason=reason or f"合并 {len(cards)} 个相似卡片",
                    changes={"merged_from": [c["evidence_id"] for c in cards]},
                ).__dict__],
                "replaced_by": "",
                "conflict_ids": [],
                "merged_from": [c["evidence_id"] for c in cards],
                "appended_evidence": [],
                "metadata": {"merge_strategy": merge_strategy},
            }

            # 把其他卡片的内容作为追加证据
            for other in others:
                merged_card["appended_evidence"].append({
                    "content": other["content_preview"],
                    "paper_id": other["paper_id"],
                    "para_id": other["para_id"],
                    "timestamp": datetime.now().isoformat(),
                    "reason": "合并自卡片 " + other["evidence_id"],
                })

            # 标记原卡片为已合并
            for c in cards:
                c["status"] = CardStatus.MERGED.value
                c["replaced_by"] = merged_id
                c["updated_at"] = datetime.now().isoformat()

            # 更新索引
            self._card_index[merged_id] = merged_card
            if section_id:
                if section_id not in self._section_cards:
                    self._section_cards[section_id] = set()
                self._section_cards[section_id].add(merged_id)

        # 记录操作日志
        affected = self._get_affected_sections(merged_id)
        self._log_operation(
            operation=CardOperationType.MERGE.value,
            card_id=merged_id,
            related_card_ids=[c["evidence_id"] for c in cards],
            reason=reason or f"合并 {len(cards)} 个相似卡片",
            affected_sections=affected,
            details={"merge_strategy": merge_strategy, "merged_count": len(cards)},
        )

        self._save_state()
        return merged_card

    # -------------------------------------------------------------------------
    # 核心操作：标记失效
    # -------------------------------------------------------------------------

    def deprecate_card(
        self,
        card_id: str,
        replaced_by: str = "",
        reason: str = "",
    ) -> bool:
        """
        标记卡片为已失效（被新证据取代）

        Args:
            card_id: 要标记的卡片 ID
            replaced_by: 取代它的新卡片 ID
            reason: 失效原因

        Returns:
            是否成功
        """
        with self._lock:
            if card_id not in self._card_index:
                return False

            card = self._card_index[card_id]
            card["status"] = CardStatus.DEPRECATED.value
            card["replaced_by"] = replaced_by
            card["updated_at"] = datetime.now().isoformat()

            # 增加版本
            new_version = CardVersion(
                version=len(card["versions"]) + 1,
                operation="deprecate",
                reason=reason or "被新证据取代",
                changes={"replaced_by": replaced_by},
            )
            card["versions"].append(new_version.__dict__)

        # 记录操作日志
        affected = self._get_affected_sections(card_id)
        self._log_operation(
            operation=CardOperationType.DEPRECATE.value,
            card_id=card_id,
            related_card_ids=[replaced_by] if replaced_by else [],
            reason=reason or "被新证据取代",
            affected_sections=affected,
            details={"replaced_by": replaced_by},
        )

        self._save_state()
        return True

    # -------------------------------------------------------------------------
    # 核心操作：标记冲突
    # -------------------------------------------------------------------------

    def flag_conflict(
        self,
        card_id_1: str,
        card_id_2: str,
        conflict_type: str = "contradiction",
        description: str = "",
        confidence: float = 0.0,
    ) -> Optional[ConflictRecord]:
        """
        标记两个卡片之间存在冲突

        Args:
            card_id_1: 卡片1 ID
            card_id_2: 卡片2 ID
            conflict_type: 冲突类型（contradiction / inconsistency / outdated）
            description: 冲突描述
            confidence: 冲突置信度

        Returns:
            冲突记录，失败返回 None
        """
        with self._lock:
            if card_id_1 not in self._card_index or card_id_2 not in self._card_index:
                return None

            conflict = ConflictRecord(
                card_id_1=card_id_1,
                card_id_2=card_id_2,
                conflict_type=conflict_type,
                description=description,
                confidence=confidence,
            )

            self._conflicts[conflict.conflict_id] = conflict

            # 在卡片上记录冲突
            for cid in [card_id_1, card_id_2]:
                if conflict.conflict_id not in self._card_index[cid]["conflict_ids"]:
                    self._card_index[cid]["conflict_ids"].append(conflict.conflict_id)
                # 如果置信度高，标记为冲突状态
                if confidence >= 0.7:
                    self._card_index[cid]["status"] = CardStatus.CONFLICT.value

        # 记录操作日志
        affected = list(set(
            self._get_affected_sections(card_id_1) +
            self._get_affected_sections(card_id_2)
        ))
        self._log_operation(
            operation=CardOperationType.FLAG_CONFLICT.value,
            card_id=card_id_1,
            related_card_ids=[card_id_2],
            reason=f"标记冲突: {description[:100]}",
            affected_sections=affected,
            details={"conflict_type": conflict_type, "confidence": confidence},
        )

        self._save_state()
        return conflict

    # -------------------------------------------------------------------------
    # 查询与统计
    # -------------------------------------------------------------------------

    def get_card(self, card_id: str) -> Optional[dict]:
        """获取卡片信息"""
        with self._lock:
            return self._card_index.get(card_id)

    def get_active_cards(self, section_id: str = "") -> list[dict]:
        """获取活跃的卡片列表"""
        with self._lock:
            if section_id:
                card_ids = self._section_cards.get(section_id, set())
                return [
                    self._card_index[cid] for cid in card_ids
                    if cid in self._card_index and
                    self._card_index[cid]["status"] == CardStatus.ACTIVE.value
                ]
            else:
                return [
                    card for card in self._card_index.values()
                    if card["status"] == CardStatus.ACTIVE.value
                ]

    def get_conflicts(
        self,
        resolved: Optional[bool] = None,
        section_id: str = "",
    ) -> list[ConflictRecord]:
        """获取冲突记录列表"""
        with self._lock:
            conflicts = list(self._conflicts.values())
            if resolved is not None:
                conflicts = [c for c in conflicts if c.resolved == resolved]
            if section_id:
                # 过滤出涉及该章节卡片的冲突
                section_card_ids = self._section_cards.get(section_id, set())
                conflicts = [
                    c for c in conflicts
                    if c.card_id_1 in section_card_ids or c.card_id_2 in section_card_ids
                ]
            return conflicts

    def get_operation_logs(
        self,
        card_id: str = "",
        operation: str = "",
        limit: int = 100,
    ) -> list[IncrementalOperationLog]:
        """获取操作日志"""
        with self._lock:
            logs = self._operation_logs[:]
            if card_id:
                logs = [
                    log for log in logs
                    if log.card_id == card_id or card_id in log.related_card_ids
                ]
            if operation:
                logs = [log for log in logs if log.operation == operation]
            return logs[-limit:]

    def get_stats(self) -> dict:
        """获取增量维护统计信息"""
        with self._lock:
            total = len(self._card_index)
            active = sum(1 for c in self._card_index.values() if c["status"] == CardStatus.ACTIVE.value)
            deprecated = sum(1 for c in self._card_index.values() if c["status"] == CardStatus.DEPRECATED.value)
            conflict = sum(1 for c in self._card_index.values() if c["status"] == CardStatus.CONFLICT.value)
            merged = sum(1 for c in self._card_index.values() if c["status"] == CardStatus.MERGED.value)
            unresolved_conflicts = sum(1 for c in self._conflicts.values() if not c.resolved)
            total_appended = sum(len(c.get("appended_evidence", [])) for c in self._card_index.values())

            return {
                "total_cards": total,
                "active_cards": active,
                "deprecated_cards": deprecated,
                "conflict_cards": conflict,
                "merged_cards": merged,
                "unresolved_conflicts": unresolved_conflicts,
                "total_appended_evidence": total_appended,
                "total_operations": len(self._operation_logs),
                "sections_affected": len(self._section_cards),
            }

    # -------------------------------------------------------------------------
    # 影响范围评估
    # -------------------------------------------------------------------------

    def assess_impact(
        self,
        card_id: str,
        review_outline: Optional[dict] = None,
    ) -> dict:
        """
        评估卡片变更的影响范围

        Args:
            card_id: 变更的卡片 ID
            review_outline: 综述大纲（可选，用于更精确的影响评估）

        Returns:
            影响范围评估结果
        """
        with self._lock:
            card = self._card_index.get(card_id)
            if not card:
                return {"error": "Card not found"}

            # 直接受影响的章节
            direct_sections = self._get_affected_sections(card_id)

            # 间接受影响的章节（同一论文的其他卡片所在章节）
            paper_id = card["paper_id"]
            related_card_ids = [
                cid for cid, c in self._card_index.items()
                if c["paper_id"] == paper_id and cid != card_id
            ]
            indirect_sections = set()
            for rid in related_card_ids:
                indirect_sections.update(self._get_affected_sections(rid))
            indirect_sections -= set(direct_sections)

            # 冲突影响
            conflict_ids = card.get("conflict_ids", [])
            related_conflicts = [
                self._conflicts[cid] for cid in conflict_ids
                if cid in self._conflicts
            ]

            return {
                "card_id": card_id,
                "card_status": card["status"],
                "direct_affected_sections": direct_sections,
                "indirect_affected_sections": list(indirect_sections),
                "related_cards_count": len(related_card_ids),
                "related_conflicts": [c.conflict_id for c in related_conflicts],
                "recommendation": self._get_impact_recommendation(card, direct_sections),
            }

    def _get_impact_recommendation(self, card: dict, sections: list[str]) -> str:
        """根据卡片状态和影响范围给出处理建议"""
        status = card["status"]
        if status == CardStatus.DEPRECATED.value:
            return f"卡片已失效，建议在 {len(sections)} 个受影响章节中替换为新证据"
        elif status == CardStatus.CONFLICT.value:
            return f"卡片存在冲突，建议人工复核后决定保留或替换"
        elif status == CardStatus.MERGED.value:
            return f"卡片已合并，受影响章节应使用合并后的新卡片"
        else:
            return f"卡片活跃，变更将影响 {len(sections)} 个章节，建议局部重算"

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _get_affected_sections(self, card_id: str) -> list[str]:
        """获取卡片影响的章节列表"""
        sections = []
        for section_id, card_ids in self._section_cards.items():
            if card_id in card_ids:
                sections.append(section_id)
        return sections

    def _log_operation(
        self,
        operation: str,
        card_id: str,
        related_card_ids: list[str] = None,
        reason: str = "",
        affected_sections: list[str] = None,
        details: dict = None,
    ):
        """记录操作日志"""
        log = IncrementalOperationLog(
            operation=operation,
            card_id=card_id,
            related_card_ids=related_card_ids or [],
            reason=reason,
            details=details or {},
            affected_sections=affected_sections or [],
        )
        self._operation_logs.append(log)

        # 限制日志数量
        if len(self._operation_logs) > self.max_logs:
            self._operation_logs = self._operation_logs[-self.max_logs:]

    def _save_state(self):
        """保存状态到磁盘"""
        try:
            state = {
                "card_index": self._card_index,
                "conflicts": {k: v.__dict__ for k, v in self._conflicts.items()},
                "operation_logs": [log.__dict__ for log in self._operation_logs],
                "section_cards": {k: list(v) for k, v in self._section_cards.items()},
                "saved_at": datetime.now().isoformat(),
            }
            state_file = self.storage_dir / "state.json"
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"⚠️  保存增量维护状态失败: {e}")

    def _load_state(self):
        """从磁盘加载状态"""
        try:
            state_file = self.storage_dir / "state.json"
            if state_file.is_file():
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)

                self._card_index = state.get("card_index", {})
                self._conflicts = {
                    k: ConflictRecord(**v) for k, v in state.get("conflicts", {}).items()
                }
                self._operation_logs = [
                    IncrementalOperationLog(**log) for log in state.get("operation_logs", [])
                ]
                self._section_cards = {
                    k: set(v) for k, v in state.get("section_cards", {}).items()
                }
        except Exception as e:
            print(f"⚠️  加载增量维护状态失败: {e}")

    def clear(self):
        """清空所有数据（慎用）"""
        with self._lock:
            self._card_index.clear()
            self._conflicts.clear()
            self._operation_logs.clear()
            self._section_cards.clear()
            self._save_state()


# =============================================================================
# 全局单例
# =============================================================================

_manager_instance: Optional[EvidenceCardIncrementalManager] = None
_manager_lock = threading.Lock()


def get_incremental_manager(relation_classifier=None) -> EvidenceCardIncrementalManager:
    """获取全局 EvidenceCard 增量维护管理器单例"""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = EvidenceCardIncrementalManager(
                    relation_classifier=relation_classifier,
                )
    return _manager_instance
