"""
V25.3 - 证据间关系抽取器（RelationExtractor）。

对证据卡片对，用 LLM 判定逻辑关系（supports / contradicts / elaborates / unrelated），
并对矛盾关系自动分析实验条件差异。这是冲突识别和综述"研究争议"章节的基础。

性能策略：
1. 生成所有证据对（O(n²)，n通常<30，可接受）
2. 关键词粗筛：无共同关键词的对直接标为 unrelated，不调用 LLM
3. 批量 LLM 判定：一次 prompt 放多对，减少 API 调用次数

用法:
    extractor = RelationExtractor(llm_client)
    relations = extractor.extract(evidence_cards)
"""

from __future__ import annotations

import re
from typing import Optional

from .models import (
    EvidenceCard,
    EvidenceRelation,
    RelationType,
)


# ──────────────────────────────────────────────
# LLM 关系判定 Prompt
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位科研文献分析专家。你的任务是判断两条来自不同论文的证据之间的逻辑关系。

关系类型定义：
- supports（支持）：一条证据的结论被另一条证据佐证、验证或一致
- contradicts（矛盾）：两条证据在**相同或高度相似的实验条件下**，对同一问题得出不一致或相反的结论
- elaborates（展开）：一条证据对另一条证据做更详细的解释、补充，或在不同实验条件下提供互补的结果
- unrelated（无关）：两条证据讨论不同的问题，没有直接逻辑关系

【判定矛盾的铁律 — 违反即误判】
在判定 contradicts 之前，你必须先检查两条证据的实验条件是否可比：
1. **突变类型不同 → 不能判矛盾**：GOF（功能获得）和 LOF（功能丧失/敲除）的结果本来就应该相反，这是不同突变类型的正常差异，不是矛盾，应判为 elaborates
2. **测量指标不同 → 不能判矛盾**：mRNA水平、总蛋白水平、磷酸化蛋白水平、功能活性是不同维度，一个升高另一个降低可能是调控机制，不是矛盾
3. **细胞类型不同 → 不能判矛盾**：不同细胞类型的表达/响应本来就可能不同，应判为 elaborates
4. **刺激条件不同 → 不能判矛盾**：IFN-α和IFN-gamma的响应不同是正常的，未刺激和刺激后的结果不同更是必然
5. **一个是正常生理状态，一个是突变/疾病状态 → 不能判矛盾**：正常人高表达 vs 患者表达受损，这是疾病导致的变化，不是矛盾

只有当两条证据的**突变类型、测量指标、细胞类型、刺激条件都相同或高度相似**，且结论相反时，才能判定为 contradicts。

对于 contradicts（矛盾）关系，你必须额外分析：
- 两条证据的实验条件有什么差异（即使判定为矛盾，也要说明条件的细微差异）
- 这些条件差异是否可能部分解释结论不同

输出严格 JSON 数组格式，每个元素对应一对证据：
[
  {
    "pair_index": 0,
    "relation": "supports|contradicts|elaborates|unrelated",
    "confidence": 0.9,
    "explanation": "简短说明判定理由，特别说明为什么条件可比或不可比",
    "condition_diff": "仅 contradicts 时填写实验条件差异分析，否则为空字符串"
  }
]
只输出 JSON，不要任何其他文字。"""


class RelationExtractor:
    """证据间关系抽取器：LLM 判定 + 关键词粗筛 + 批量调用。"""

    def __init__(
        self,
        llm_client=None,
        batch_size: int = 5,
        min_keyword_overlap: int = 1,
    ):
        """
        Args:
            llm_client: LLMClient 实例（为 None 时只做关键词粗筛，所有通过粗筛的对标为 elaborates）
            batch_size: 每次 LLM 调用处理的证据对数量
            min_keyword_overlap: 关键词粗筛的最低共同关键词数
        """
        self.llm = llm_client
        self.batch_size = batch_size
        self.min_keyword_overlap = min_keyword_overlap

    def extract(self, evidence_cards: list[EvidenceCard]) -> list[EvidenceRelation]:
        """
        从证据卡片列表中抽取所有两两关系。

        Args:
            evidence_cards: 证据卡片列表

        Returns:
            EvidenceRelation 列表（只包含非 unrelated 的关系，unrelated 不返回以节省空间）
        """
        if len(evidence_cards) < 2:
            return []

        # Step 1: 生成所有证据对
        pairs = self._generate_pairs(evidence_cards)
        if not pairs:
            return []

        # Step 2: 关键词粗筛
        candidates, unrelated_pairs = self._keyword_filter(pairs, evidence_cards)

        # 统一的关系列表（所有类型的关系都往这里加）
        relations: list[EvidenceRelation] = []

        # Step 2.5: 跨论文优化——同一论文内的证据对直接标为 elaborates，不调 LLM
        # （同一篇论文内的证据大概率是展开/补充关系，不需要LLM判定，可减少50%+调用）
        cross_paper_candidates = []
        same_paper_pairs = []
        for src_idx, tgt_idx in candidates:
            src_pid = (evidence_cards[src_idx].paper_id or "").strip()
            tgt_pid = (evidence_cards[tgt_idx].paper_id or "").strip()
            if src_pid and tgt_pid and src_pid == tgt_pid:
                same_paper_pairs.append((src_idx, tgt_idx))
            else:
                cross_paper_candidates.append((src_idx, tgt_idx))

        # 同一论文内的对标为 elaborates
        for src_idx, tgt_idx in same_paper_pairs:
            src = evidence_cards[src_idx]
            tgt = evidence_cards[tgt_idx]
            relations.append(EvidenceRelation(
                relation_id=f"rel_{src.evidence_id}_{tgt.evidence_id}",
                source_evidence_id=src.evidence_id,
                target_evidence_id=tgt.evidence_id,
                relation_type=RelationType.ELABORATES,
                confidence=0.6,
                explanation="同一论文内证据，默认标为展开",
            ))

        # 粗筛判定为 unrelated 的直接生成关系对象
        for src_idx, tgt_idx in unrelated_pairs:
            src = evidence_cards[src_idx]
            tgt = evidence_cards[tgt_idx]
            relations.append(EvidenceRelation(
                relation_id=f"rel_{src.evidence_id}_{tgt.evidence_id}",
                source_evidence_id=src.evidence_id,
                target_evidence_id=tgt.evidence_id,
                relation_type=RelationType.UNRELATED,
                confidence=0.5,
                explanation="关键词粗筛判定为无关",
            ))

        # Step 3: LLM 判定（批量，只对跨论文对判定）
        if cross_paper_candidates and self.llm and self.llm.is_available():
            llm_relations = self._llm_judge_batch(cross_paper_candidates, evidence_cards)
            relations.extend(llm_relations)
        else:
            # LLM 不可用：跨论文对默认标为 elaborates（保守估计）
            for src_idx, tgt_idx in cross_paper_candidates:
                src = evidence_cards[src_idx]
                tgt = evidence_cards[tgt_idx]
                relations.append(EvidenceRelation(
                    relation_id=f"rel_{src.evidence_id}_{tgt.evidence_id}",
                    source_evidence_id=src.evidence_id,
                    target_evidence_id=tgt.evidence_id,
                    relation_type=RelationType.ELABORATES,
                    confidence=0.3,
                    explanation="LLM不可用，关键词粗筛通过，默认标为展开",
                ))

        return relations

    def get_contradictions(self, relations: list[EvidenceRelation]) -> list[EvidenceRelation]:
        """筛选出所有矛盾关系。"""
        return [r for r in relations if r.relation_type == RelationType.CONTRADICTS]

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    @staticmethod
    def _generate_pairs(cards: list[EvidenceCard]) -> list[tuple[int, int]]:
        """生成所有证据对索引（上三角，不重复）。"""
        pairs = []
        n = len(cards)
        for i in range(n):
            for j in range(i + 1, n):
                pairs.append((i, j))
        return pairs

    def _keyword_filter(
        self,
        pairs: list[tuple[int, int]],
        cards: list[EvidenceCard],
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """
        关键词粗筛：计算两条证据的关键词重叠数。
        重叠数 >= min_keyword_overlap 的进入 LLM 判定，否则直接标为 unrelated。
        """
        candidates = []
        unrelated = []

        # 预计算每条证据的关键词集合
        keywords_list = [self._extract_keywords(c.content + " " + c.original_quote) for c in cards]

        for src_idx, tgt_idx in pairs:
            overlap = len(keywords_list[src_idx] & keywords_list[tgt_idx])
            if overlap >= self.min_keyword_overlap:
                candidates.append((src_idx, tgt_idx))
            else:
                unrelated.append((src_idx, tgt_idx))

        return candidates, unrelated

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """从文本中提取关键词（简单实现：取长度>=4的英文单词和中文词组）。"""
        # 英文单词（长度>=4）
        english_words = set(w.lower() for w in re.findall(r'[a-zA-Z]{4,}', text))
        # 过滤常见停用词
        stopwords = {'that', 'this', 'with', 'from', 'were', 'which', 'their', 'have', 'been', 'they', 'also', 'more', 'such', 'than', 'these', 'those', 'into', 'about', 'other', 'between', 'during', 'because', 'through', 'before', 'after', 'above', 'below'}
        english_words -= stopwords
        return english_words

    def _llm_judge_batch(
        self,
        candidates: list[tuple[int, int]],
        cards: list[EvidenceCard],
    ) -> list[EvidenceRelation]:
        """批量调用 LLM 判定证据对关系。"""
        relations = []

        for batch_start in range(0, len(candidates), self.batch_size):
            batch = candidates[batch_start:batch_start + self.batch_size]

            # 构建 prompt
            pair_descriptions = []
            for pair_idx, (src_idx, tgt_idx) in enumerate(batch):
                src = cards[src_idx]
                tgt = cards[tgt_idx]
                pair_descriptions.append(
                    f"--- 证据对 {pair_idx} ---\n"
                    f"[证据A] 类型={src.evidence_type.value}\n"
                    f"  内容: {src.content[:200]}\n"
                    f"  实验条件: 模型={src.model_system or '未知'}, 样本={src.sample_size or '未知'}, "
                    f"处理={src.treatment or '未知'}, 时间点={src.time_point or '未知'}\n"
                    f"  细粒度条件: 突变类型={src.mutation_type or '未知'}, 细胞类型={src.cell_type or '未知'}, "
                    f"测量指标={src.measurement or '未知'}, 刺激条件={src.stimulus or '未知'}\n"
                    f"[证据B] 类型={tgt.evidence_type.value}\n"
                    f"  内容: {tgt.content[:200]}\n"
                    f"  实验条件: 模型={tgt.model_system or '未知'}, 样本={tgt.sample_size or '未知'}, "
                    f"处理={tgt.treatment or '未知'}, 时间点={tgt.time_point or '未知'}\n"
                    f"  细粒度条件: 突变类型={tgt.mutation_type or '未知'}, 细胞类型={tgt.cell_type or '未知'}, "
                    f"测量指标={tgt.measurement or '未知'}, 刺激条件={tgt.stimulus or '未知'}"
                )

            user_prompt = "请判断以下证据对之间的逻辑关系：\n\n" + "\n\n".join(pair_descriptions)

            try:
                results = self.llm.chat_json(SYSTEM_PROMPT, user_prompt)
                if not isinstance(results, list):
                    continue

                for item in results:
                    if not isinstance(item, dict):
                        continue
                    pair_idx = item.get("pair_index", -1)
                    if pair_idx < 0 or pair_idx >= len(batch):
                        continue

                    src_idx, tgt_idx = batch[pair_idx]
                    src = cards[src_idx]
                    tgt = cards[tgt_idx]

                    rel_type_str = item.get("relation", "unrelated").lower().strip()
                    rel_type = self._parse_relation_type(rel_type_str)
                    explanation = item.get("explanation", "")[:300]
                    condition_diff = item.get("condition_diff", "")[:300]

                    # V25.5: 条件差异标记——不强制过滤，而是分类呈现
                    # 如果 LLM 判定为 contradicts，但两条证据的关键条件明显不同，
                    # 保留 contradicts 关系类型，但标记 condition_mismatch=True，
                    # 后续 conflict_detector 会把这类单独放进"不同实验条件下的结果差异"章节，
                    # 而不是放进"研究争议"章节
                    condition_mismatch = False
                    mismatch_reason = ""
                    if rel_type == RelationType.CONTRADICTS:
                        mismatch_reason = self._check_condition_incomparability(src, tgt)
                        if mismatch_reason:
                            condition_mismatch = True
                            explanation = f"[条件差异型] 结论相反但{mismatch_reason}，属于不同条件下的不同结果，非真矛盾。原判定理由：{explanation}"

                    relations.append(EvidenceRelation(
                        relation_id=f"rel_{src.evidence_id}_{tgt.evidence_id}",
                        source_evidence_id=src.evidence_id,
                        target_evidence_id=tgt.evidence_id,
                        relation_type=rel_type,
                        confidence=item.get("confidence", 0.5),
                        explanation=explanation,
                        condition_diff=condition_diff,
                        condition_mismatch=condition_mismatch,
                        mismatch_reason=mismatch_reason,
                    ))

            except Exception:
                # LLM 调用失败，跳过这批（不中断整个流程）
                continue

        return relations

    @staticmethod
    def _parse_relation_type(raw: str) -> RelationType:
        """解析关系类型，容错处理。"""
        mapping = {
            "supports": RelationType.SUPPORTS,
            "support": RelationType.SUPPORTS,
            "contradicts": RelationType.CONTRADICTS,
            "contradict": RelationType.CONTRADICTS,
            "conflict": RelationType.CONTRADICTS,
            "elaborates": RelationType.ELABORATES,
            "elaborate": RelationType.ELABORATES,
            "unrelated": RelationType.UNRELATED,
        }
        return mapping.get(raw.lower().strip(), RelationType.UNRELATED)

    @staticmethod
    def _check_condition_incomparability(src: EvidenceCard, tgt: EvidenceCard) -> str:
        """V25.5: 检查两条证据的实验条件是否明显不可比。
        如果明显不可比，返回降级原因字符串；否则返回空字符串。

        只在条件差异非常明确时才降级，避免误杀真正的矛盾。
        """
        reasons = []

        # 1. 突变类型：GOF vs LOF/缺陷/敲除 → 明显不可比
        src_mut = (src.mutation_type or "").lower()
        tgt_mut = (tgt.mutation_type or "").lower()
        is_gof = lambda m: "gof" in m or "功能获得" in m or "获得性" in m
        is_lof = lambda m: "lof" in m or "功能丧失" in m or "缺陷" in m or "敲除" in m or "缺失" in m or "loss" in m
        if (is_gof(src_mut) and is_lof(tgt_mut)) or (is_lof(src_mut) and is_gof(tgt_mut)):
            reasons.append(f"突变类型不同（{src.mutation_type} vs {tgt.mutation_type}）")

        # 2. 一个是正常生理（不适用），一个是突变/疾病 → 明显不可比
        is_normal = lambda m: "不适用" in m or "正常" in m or "生理" in m or "wild" in m or "wt" in m
        is_mutant = lambda m: "突变" in m or "患者" in m or "疾病" in m or "gof" in m or "lof" in m or "缺陷" in m
        if (is_normal(src_mut) and is_mutant(tgt_mut)) or (is_mutant(src_mut) and is_normal(tgt_mut)):
            reasons.append(f"生理状态不同（{src.mutation_type} vs {tgt.mutation_type}）")

        # 3. 测量指标：mRNA vs 蛋白/磷酸化/功能 → 不同维度，不可比
        src_meas = (src.measurement or "").lower()
        tgt_meas = (tgt.measurement or "").lower()
        is_mrna = lambda m: "mrna" in m or "转录" in m or "rna" in m
        is_protein = lambda m: "蛋白" in m or "protein" in m or "磷酸化" in m or "phosphor" in m or "表达" in m
        is_function = lambda m: "功能" in m or "活性" in m or "function" in m or "activity" in m or "临床" in m or "表型" in m
        if (is_mrna(src_meas) and (is_protein(tgt_meas) or is_function(tgt_meas))) or \
           ((is_protein(src_meas) or is_function(src_meas)) and is_mrna(tgt_meas)):
            reasons.append(f"测量指标维度不同（{src.measurement} vs {tgt.measurement}）")

        # 4. 刺激条件：未刺激 vs 明确刺激 → 基线 vs 响应，不可比
        src_stim = (src.stimulus or "").lower()
        tgt_stim = (tgt.stimulus or "").lower()
        is_unstimulated = lambda s: "未刺激" in s or "基线" in s or "unstim" in s or "baseline" in s or "对照" in s
        is_stimulated = lambda s: "刺激" in s or "ifn" in s or "干扰素" in s or "感染" in s or "处理" in s
        if (is_unstimulated(src_stim) and is_stimulated(tgt_stim)) or \
           (is_stimulated(src_stim) and is_unstimulated(tgt_stim)):
            reasons.append(f"刺激条件不同（{src.stimulus} vs {tgt.stimulus}）")

        if reasons:
            return "；".join(reasons)
        return ""


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("🔗 Relation Extractor Test (V25.3)")
    print("=" * 60)

    # 构造测试证据卡片
    test_cards = [
        EvidenceCard(
            evidence_id="ev_001", paper_id="paper1", para_id="p1",
            evidence_type="fact",
            content="STAT1 knockout mice are highly susceptible to viral infections.",
            original_quote="STAT1 knockout mice are highly susceptible to viral infections.",
            model_system="小鼠", sample_size="n=10",
        ),
        EvidenceCard(
            evidence_id="ev_002", paper_id="paper2", para_id="p1",
            evidence_type="fact",
            content="STAT1 deficiency in humans causes severe viral and mycobacterial infections.",
            original_quote="STAT1 deficiency causes severe infections.",
            model_system="人类患者", sample_size="n=5",
        ),
        EvidenceCard(
            evidence_id="ev_003", paper_id="paper3", para_id="p1",
            evidence_type="claim",
            content="STAT1 is not essential for antiviral immunity in epithelial cells.",
            original_quote="STAT1 is not essential in epithelial cells.",
            model_system="细胞系", sample_size="n=3",
        ),
        EvidenceCard(
            evidence_id="ev_004", paper_id="paper1", para_id="p2",
            evidence_type="mechanism",
            content="STAT1 is phosphorylated at Y701 by JAK kinases upon IFN-gamma stimulation.",
            original_quote="STAT1 is phosphorylated at Y701.",
        ),
        EvidenceCard(
            evidence_id="ev_005", paper_id="paper4", para_id="p1",
            evidence_type="background",
            content="The JAK-STAT pathway is a conserved signaling cascade in eukaryotes.",
            original_quote="JAK-STAT is conserved.",
        ),
    ]

    # 测试无 LLM 模式（关键词粗筛 + 默认 elaborates）
    extractor = RelationExtractor(llm_client=None)
    relations = extractor.extract(test_cards)

    print(f"\n证据卡片数: {len(test_cards)}")
    print(f"证据对总数: {len(test_cards) * (len(test_cards) - 1) // 2}")
    print(f"抽取到关系数: {len(relations)}")

    # 按类型统计
    type_counts = {}
    for r in relations:
        type_counts[r.relation_type.value] = type_counts.get(r.relation_type.value, 0) + 1
    print(f"关系类型分布: {type_counts}")

    # 展示非 unrelated 的关系
    print("\n非无关关系:")
    for r in relations:
        if r.relation_type != RelationType.UNRELATED:
            print(f"  [{r.relation_type.value}] {r.source_evidence_id} ↔ {r.target_evidence_id} "
                  f"(conf={r.confidence}) — {r.explanation[:50]}")

    print("\n✅ 关系抽取测试完成（无 LLM 模式）。")
    print("   LLM 模式需要 Ollama 服务运行，可判定 supports/contradicts/elaborates 并分析实验条件差异。")
