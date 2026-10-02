"""
V25.6 - 综述结果暂存模块（ReviewStore）。

独立模块，不污染综述生成主流程。负责：
1. 生成综述后暂存完整结果（含 sentences 和 evidence_cards，用于点击溯源）
2. 按 review_id 检索综述详情
3. 按 sentence_id 检索单个句子的溯源信息
4. 按 evidence_id 检索证据卡片详情

设计原则：
- 内存存储，带 TTL 自动过期（默认 1 小时），避免内存泄漏
- 线程安全（Flask 单线程模式下其实不需要，但保留锁以兼容未来多线程）
- 不修改现有 ReviewOutput 模型，而是在暂存时额外保存 draft 和 evidence_cards
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from .models import EvidenceCard, ReviewOutput, ReviewDraft


class ReviewStore:
    """综述结果暂存器（内存 + TTL）。"""

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 100):
        """
        Args:
            ttl_seconds: 综述结果过期时间（秒），默认 1 小时
            max_entries: 最大暂存数量，超过后清理最旧的
        """
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()

    def store(
        self,
        review_output: ReviewOutput,
        draft: ReviewDraft,
        evidence_cards: list[EvidenceCard],
    ) -> str:
        """暂存综述结果，返回 review_id。

        Args:
            review_output: 综述输出（含 markdown、stats、warnings 等）
            draft: 综述初稿（含 sentences，用于溯源）
            evidence_cards: 证据卡片列表（用于溯源）

        Returns:
            review_id: 综述唯一 ID
        """
        review_id = f"rev_{uuid.uuid4().hex[:12]}"

        # 构建证据卡片字典（短 ID -> 卡片）
        evidence_dict = {c.evidence_id: c for c in evidence_cards}

        # 构建句子列表（含溯源信息）
        sentences = []
        for s in draft.sentences:
            sentences.append({
                "sentence_id": s.sentence_id,
                "section_id": s.section_id,
                "text": s.text,
                "evidence_ids": s.evidence_ids,
                "status": s.status.value,
                "verification_note": s.verification_note,
            })

        entry = {
            "review_id": review_id,
            "created_at": time.time(),
            "topic": review_output.topic,
            "markdown": review_output.markdown,
            "references": review_output.references,
            "stats": review_output.stats,
            "warnings": review_output.warnings,
            "relations": review_output.relations,
            "conflicts": review_output.conflicts,
            "sentences": sentences,
            "evidence_cards": {
                eid: {
                    "evidence_id": c.evidence_id,
                    "paper_id": c.paper_id,
                    "para_id": c.para_id,
                    "paper_title": c.paper_title,
                    "section_l1": c.section_l1,
                    "page": c.page,
                    "content": c.content,
                    "original_quote": c.original_quote,
                    "evidence_type": c.evidence_type.value,
                    "mutation_type": c.mutation_type,
                    "cell_type": c.cell_type,
                    "measurement": c.measurement,
                    "stimulus": c.stimulus,
                    "model_system": c.model_system,
                    "sentence_start": c.sentence_start,
                    "sentence_end": c.sentence_end,
                }
                for eid, c in evidence_dict.items()
            },
        }

        with self._lock:
            # 清理过期条目
            self._cleanup_expired_locked()
            # 如果超过最大数量，清理最旧的
            if len(self._store) >= self.max_entries:
                oldest_id = min(self._store.keys(), key=lambda k: self._store[k]["created_at"])
                del self._store[oldest_id]
            # 存储新条目
            self._store[review_id] = entry

        return review_id

    def get(self, review_id: str) -> Optional[dict]:
        """获取综述详情。

        Args:
            review_id: 综述 ID

        Returns:
            综述详情字典，不存在或已过期返回 None
        """
        with self._lock:
            entry = self._store.get(review_id)
            if entry is None:
                return None
            # 检查是否过期
            if time.time() - entry["created_at"] > self.ttl:
                del self._store[review_id]
                return None
            return entry

    def get_sentence(self, review_id: str, sentence_id: str) -> Optional[dict]:
        """获取单个句子的溯源信息。

        Args:
            review_id: 综述 ID
            sentence_id: 句子 ID

        Returns:
            句子详情 + 关联的证据卡片列表，不存在返回 None
        """
        entry = self.get(review_id)
        if entry is None:
            return None

        sentence = next((s for s in entry["sentences"] if s["sentence_id"] == sentence_id), None)
        if sentence is None:
            return None

        # 关联证据卡片
        evidences = []
        for eid in sentence["evidence_ids"]:
            ev = entry["evidence_cards"].get(eid)
            if ev:
                evidences.append(ev)

        return {
            "sentence": sentence,
            "evidences": evidences,
        }

    def get_evidence(self, review_id: str, evidence_id: str) -> Optional[dict]:
        """获取单个证据卡片详情。

        Args:
            review_id: 综述 ID
            evidence_id: 证据 ID

        Returns:
            证据卡片字典，不存在返回 None
        """
        entry = self.get(review_id)
        if entry is None:
            return None
        return entry["evidence_cards"].get(evidence_id)

    def _cleanup_expired_locked(self) -> None:
        """清理过期条目（调用者必须持有锁）。"""
        now = time.time()
        expired = [rid for rid, entry in self._store.items() if now - entry["created_at"] > self.ttl]
        for rid in expired:
            del self._store[rid]

    def stats(self) -> dict:
        """获取暂存器统计信息。"""
        with self._lock:
            return {
                "total_entries": len(self._store),
                "ttl_seconds": self.ttl,
                "max_entries": self.max_entries,
            }


# 全局单例
_review_store: Optional[ReviewStore] = None


def get_review_store() -> ReviewStore:
    """获取全局综述暂存器单例。"""
    global _review_store
    if _review_store is None:
        _review_store = ReviewStore()
    return _review_store
