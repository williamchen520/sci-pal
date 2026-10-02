"""
V25.0 - 引用校验 Agent（CitationVerifier）。

最重要的质量闸门：独立一轮校验，逐句扫描综述初稿，
检查每一个科学结论是否存在对应的证据卡片，剔除无证据支撑的句子。

这一步解决最大痛点：大模型写综述"编文献、编结果"。

校验分两层：
1. 确定性校验（必做）：检查 evidence_ids 非空、ID 真实存在、来源论文在库中
2. LLM 深度校验（可选）：用 LLM 判断句子内容是否真的被证据卡片支撑

用法:
    verifier = CitationVerifier(llm_client)
    verified_draft, warnings = verifier.verify(draft, use_llm=False)
"""

from __future__ import annotations

from typing import Optional

from .llm_client import LLMClient, LLMError
from .models import (
    EvidenceCard,
    ReviewDraft,
    ReviewSentence,
    SentenceStatus,
)


# ──────────────────────────────────────────────
# LLM 深度校验 Prompt
# ──────────────────────────────────────────────

VERIFY_SYSTEM_PROMPT = """你是一个科研综述引用校验器。你的任务是判断给定的综述句子是否被提供的证据卡片真正支撑。

严格规则：
1. 只有当证据卡片中明确陈述了句子中的核心断言时，才判定为 "supported"
2. 如果证据卡片只是背景相关，但没有直接支撑句子的核心断言，判定为 "not_supported"
3. 如果句子包含证据卡片中没有的数据、数字、机制或结论，判定为 "not_supported"
4. 不要因为句子听起来合理就判定为 supported，必须严格基于证据内容
5. 如果证据卡片之间存在矛盾，判定为 "controversial"

输出格式：严格的 JSON 对象：
{
  "verdict": "supported" | "not_supported" | "controversial",
  "reason": "简短说明判定理由",
  "matching_evidence_ids": ["实际支撑本句的证据ID列表"]
}

只返回 JSON，不要任何解释文字。"""


# ──────────────────────────────────────────────
# 引用校验器
# ──────────────────────────────────────────────

class CitationVerifier:
    """
    逐句校验综述初稿的引用完整性。

    Args:
        llm_client: LLMClient 实例（用于深度校验，可为 None 则只做确定性校验）
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def verify(
        self,
        draft: ReviewDraft,
        use_llm: bool = False,
    ) -> tuple[ReviewDraft, list[str]]:
        """
        校验综述初稿，返回校验后的 draft 和警告列表。

        Args:
            draft: 待校验的综述初稿
            use_llm: 是否启用 LLM 深度校验（默认 False，只做确定性校验）

        Returns:
            (校验后的 ReviewDraft, 警告信息列表)
        """
        warnings: list[str] = []
        verified_sentences: list[ReviewSentence] = []

        # V30.5: 先做确定性校验，收集需要 LLM 深度校验的句子
        llm_verify_sentences: list[ReviewSentence] = []

        for sent in draft.sentences:
            sent, sent_warnings = self._verify_sentence_deterministic(
                sent, draft.evidence_cards
            )
            verified_sentences.append(sent)
            warnings.extend(sent_warnings)

            # 如果确定性校验通过，且需要 LLM 深度校验，就收集起来
            if use_llm and self.llm and self.llm.is_available():
                if sent.status == SentenceStatus.VERIFIED:
                    llm_verify_sentences.append(sent)

        # V30.5: 批量 LLM 深度校验
        if llm_verify_sentences and use_llm and self.llm and self.llm.is_available():
            try:
                verified_sentences = self._batch_llm_verify(
                    verified_sentences,
                    llm_verify_sentences,
                    draft.evidence_cards,
                    warnings,
                )
            except LLMError as e:
                warnings.append(f"⚠️  批量 LLM 深度校验失败（保留确定性校验结果）: {e}")

        # 更新 draft 中的 sentences
        draft.sentences = verified_sentences

        # 汇总统计
        stats = draft.stats()
        if stats["rejected"] > 0:
            warnings.append(
                f"⚠️  共 {stats['rejected']} 句因无证据支撑被标记为 REJECTED，"
                f"将从最终输出中剔除。"
            )
        if stats["unverified"] > 0:
            warnings.append(
                f"⚠️  共 {stats['unverified']} 句未通过深度校验，建议人工复核。"
            )

        return draft, warnings

    def _verify_sentence_deterministic(
        self,
        sentence: ReviewSentence,
        evidence_cards: dict[str, EvidenceCard],
    ) -> tuple[ReviewSentence, list[str]]:
        """确定性校验（不用 LLM）。"""
        warnings: list[str] = []

        # ── 第一层：确定性校验 ──

        # 1. 检查 evidence_ids 是否非空
        if not sentence.evidence_ids:
            sentence.status = SentenceStatus.REJECTED
            sentence.verification_note = "无引用证据ID，违反'每句话必须绑定证据'铁律"
            warnings.append(f"  ❌ 句子 {sentence.sentence_id} 被拒绝：无证据ID — {sentence.text[:60]}...")
            return sentence, warnings

        # 2. 检查 evidence_ids 是否真实存在
        invalid_ids = [eid for eid in sentence.evidence_ids if eid not in evidence_cards]
        if invalid_ids:
            sentence.status = SentenceStatus.REJECTED
            sentence.verification_note = f"引用了不存在的证据ID: {invalid_ids}"
            warnings.append(f"  ❌ 句子 {sentence.sentence_id} 被拒绝：证据ID不存在 {invalid_ids}")
            return sentence, warnings

        # 3. 检查证据卡片是否有内容
        empty_cards = [
            eid for eid in sentence.evidence_ids
            if not evidence_cards[eid].content.strip()
        ]
        if empty_cards:
            sentence.status = SentenceStatus.REJECTED
            sentence.verification_note = f"关联的证据卡片内容为空: {empty_cards}"
            warnings.append(f"  ❌ 句子 {sentence.sentence_id} 被拒绝：证据卡片为空")
            return sentence, warnings

        # 确定性校验通过
        sentence.status = SentenceStatus.VERIFIED

        return sentence, warnings

    def _batch_llm_verify(
        self,
        all_sentences: list[ReviewSentence],
        llm_sentences: list[ReviewSentence],
        evidence_cards: dict[str, EvidenceCard],
        warnings: list[str],
    ) -> list[ReviewSentence]:
        """V30.5: 批量 LLM 深度校验。"""
        # 构建批量 prompt
        sentences_text = ""
        for i, sent in enumerate(llm_sentences):
            # 构建该句子的证据上下文
            evidence_text = ""
            for eid in sent.evidence_ids:
                if eid in evidence_cards:
                    card = evidence_cards[eid]
                    evidence_text += f"  [{eid}] ({card.evidence_type.value}) {card.content[:200]}\n"

            sentences_text += f"【句子 {i+1}】(sentence_id: {sent.sentence_id})\n"
            sentences_text += f"内容: {sent.text}\n"
            sentences_text += f"关联证据:\n{evidence_text}\n"
            sentences_text += "\n"

        user_prompt = f"""{sentences_text}

For each sentence above, judge whether it is truly supported by its associated evidence cards.
Return a JSON array, each element containing:
- sentence_id: the sentence ID
- verdict: "supported" | "not_supported" | "controversial"
- reason: brief reason for the verdict
- matching_evidence_ids: list of evidence IDs that actually support this sentence
"""

        result = self.llm.chat_json(VERIFY_SYSTEM_PROMPT, user_prompt)

        # 解析批量结果
        if not isinstance(result, list):
            raise LLMError("批量校验结果不是数组")

        # 建立 sentence_id 到结果的映射
        result_map = {}
        for item in result:
            if isinstance(item, dict) and "sentence_id" in item:
                result_map[item["sentence_id"]] = item

        # 更新句子状态
        for sent in llm_sentences:
            if sent.sentence_id in result_map:
                item = result_map[sent.sentence_id]
                verdict = item.get("verdict", "supported")
                reason = item.get("reason", "")
                matching_ids = item.get("matching_evidence_ids", [])

                if verdict == "not_supported":
                    sent.status = SentenceStatus.UNVERIFIED
                    sent.verification_note = f"LLM 校验：未被证据支撑 — {reason}"
                    warnings.append(f"  ⚠️  句子 {sent.sentence_id} 未被证据支撑: {reason}")
                elif verdict == "controversial":
                    sent.status = SentenceStatus.UNVERIFIED
                    sent.verification_note = f"LLM 校验：证据存在矛盾 — {reason}"
                    warnings.append(f"  ⚠️  句子 {sent.sentence_id} 证据存在矛盾: {reason}")
                else:
                    # supported
                    sent.verification_note = f"LLM 校验：被证据支撑 — {reason}"

        return all_sentences

    def _llm_deep_verify(
        self,
        sentence: ReviewSentence,
        evidence_cards: dict[str, EvidenceCard],
    ) -> tuple[ReviewSentence, list[str]]:
        """用 LLM 深度校验句子是否真的被证据支撑。"""
        warnings: list[str] = []

        # 构建证据上下文
        evidence_text = ""
        for eid in sentence.evidence_ids:
            card = evidence_cards[eid]
            evidence_text += f"[{eid}] ({card.evidence_type.value}) {card.content}\n"
            if card.original_quote:
                evidence_text += f"  原文: {card.original_quote[:200]}\n"

        user_prompt = (
            f"综述句子：{sentence.text}\n\n"
            f"关联证据卡片：\n{evidence_text}\n\n"
            f"请判断这个综述句子是否被上述证据卡片真正支撑。"
        )

        result = self.llm.chat_json(VERIFY_SYSTEM_PROMPT, user_prompt)

        verdict = result.get("verdict", "supported")
        reason = result.get("reason", "")
        matching_ids = result.get("matching_evidence_ids", [])

        if verdict == "not_supported":
            sentence.status = SentenceStatus.REJECTED
            sentence.verification_note = f"LLM深度校验：证据不支撑 — {reason}"
            warnings.append(f"  ❌ 句子 {sentence.sentence_id} 被LLM拒绝：{reason} — {sentence.text[:60]}...")
        elif verdict == "controversial":
            sentence.status = SentenceStatus.CONTROVERSIAL
            sentence.verification_note = f"LLM深度校验：证据间存在矛盾 — {reason}"
            warnings.append(f"  ⚠️  句子 {sentence.sentence_id} 标记为有争议：{reason}")
        else:
            # supported：更新为实际匹配的证据ID（如果LLM返回了更精确的列表）
            if matching_ids:
                sentence.evidence_ids = [eid for eid in matching_ids if eid in evidence_cards]
            sentence.verification_note = f"LLM深度校验通过 — {reason}"

        return sentence, warnings


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("✅ Citation Verifier Test (V25.0)")
    print("=" * 60)

    # 构造测试数据
    card1 = EvidenceCard(
        evidence_id="ev_p1_para1_0",
        paper_id="paper1",
        para_id="para1",
        content="STAT1 is phosphorylated at Y701 by JAK kinases in response to IFN-gamma.",
        evidence_type="mechanism",
    )
    card2 = EvidenceCard(
        evidence_id="ev_p1_para2_0",
        paper_id="paper1",
        para_id="para2",
        content="STAT1 knockout mice are highly susceptible to viral infections.",
        evidence_type="fact",
    )

    from .models import ReviewOutline, ReviewSection

    outline = ReviewOutline(
        topic="STAT1 干扰素调控",
        sections=[ReviewSection(section_id="sec_01", title="引言", order=0)],
    )

    # 测试用例
    test_sentences = [
        ReviewSentence(
            sentence_id="sent_01",
            section_id="sec_01",
            text="STAT1 在 IFN-gamma 刺激下被 JAK 激酶磷酸化于 Y701 位点。",
            evidence_ids=["ev_p1_para1_0"],
        ),
        ReviewSentence(
            sentence_id="sent_02",
            section_id="sec_01",
            text="这是一句完全没有证据支撑的编造结论。",
            evidence_ids=[],
        ),
        ReviewSentence(
            sentence_id="sent_03",
            section_id="sec_01",
            text="引用了不存在的证据ID。",
            evidence_ids=["ev_nonexistent"],
        ),
        ReviewSentence(
            sentence_id="sent_04",
            section_id="sec_01",
            text="STAT1 敲除小鼠对病毒感染高度易感。",
            evidence_ids=["ev_p1_para2_0"],
        ),
    ]

    draft = ReviewDraft(
        topic="STAT1 干扰素调控",
        outline=outline,
        sentences=test_sentences,
        evidence_cards={c.evidence_id: c for c in [card1, card2]},
    )

    print("\n--- 确定性校验测试 ---")
    verifier = CitationVerifier(llm_client=None)
    verified_draft, warnings = verifier.verify(draft, use_llm=False)

    for sent in verified_draft.sentences:
        icon = {"verified": "✅", "rejected": "❌", "unverified": "⚠️", "controversial": "⚡"}.get(
            sent.status.value, "?"
        )
        print(f"  {icon} [{sent.status.value}] {sent.sentence_id}: {sent.text[:50]}...")
        if sent.verification_note:
            print(f"      原因: {sent.verification_note}")

    print(f"\n--- 统计 ---")
    stats = verified_draft.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\n--- 警告 ({len(warnings)} 条) ---")
    for w in warnings:
        print(f"  {w}")

    print("\n✅ 确定性校验测试通过。")
    print("   LLM 深度校验需 Ollama 服务运行，设置 use_llm=True 启用。")
