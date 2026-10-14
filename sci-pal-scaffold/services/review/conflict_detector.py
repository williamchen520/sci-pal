"""
V25.3 - 冲突识别 Agent（ConflictDetector）。

基于证据间的 contradicts 关系，自动汇总矛盾点，标注实验条件差异，
生成可直接写入综述"研究争议"章节的争议小结。

核心价值：自动发现文献间的观点冲突，而不是让 LLM 在撰写时"自由发挥"
编造争议。所有争议点都绑定具体证据ID和实验条件差异，可溯源、可验证。

用法:
    detector = ConflictDetector(llm_client)
    conflicts = detector.detect(evidence_cards, relations)
"""

from __future__ import annotations

from typing import Optional

from .models import (
    Conflict,
    EvidenceCard,
    EvidenceRelation,
    RelationType,
)


# ──────────────────────────────────────────────
# LLM 冲突汇总 Prompt
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位科研综述写作专家。你的任务是分析文献间的矛盾关系，汇总为结构化的争议点。

给定一组矛盾证据对（每对包含两条结论不一致的证据及其实验条件），请：
1. 将相关的矛盾对聚类为争议点（讨论同一问题的矛盾对应归为同一个争议点）
2. 为每个争议点生成：
   - topic：一句话概括在争论什么
   - summary：争议小结（学术综述风格，客观陈述各方观点，不偏袒任何一方，可直接写入"研究争议"章节）
   - condition_analysis：实验条件差异分析（样本量、实验模型、处理方式、时间点、测量方法等差异如何可能导致结论不同）
   - sides：争议各方观点列表，每方包含 side（如"观点A"/"观点B"）、evidence_ids（支撑该观点的证据ID列表）、claim（该观点的核心主张）

输出严格 JSON 数组格式：
[
  {
    "topic": "争议点主题",
    "summary": "争议小结文本...",
    "condition_analysis": "实验条件差异分析...",
    "sides": [
      {"side": "观点A", "evidence_ids": ["ev_001"], "claim": "核心主张A"},
      {"side": "观点B", "evidence_ids": ["ev_003"], "claim": "核心主张B"}
    ]
  }
]
只输出 JSON，不要任何其他文字。如果矛盾对之间没有关联，每个矛盾对单独成为一个争议点。"""

SYSTEM_PROMPT_EN = """You are an expert scientific review writer. Your task is to analyze contradictory relationships between literature findings and synthesize them into structured controversy points.

Given a set of contradictory evidence pairs (each pair contains two pieces of evidence with inconsistent conclusions and their experimental conditions), please:
1. Cluster related contradictory pairs into controversy points (pairs discussing the same issue should be grouped into the same controversy point)
2. For each controversy point, generate:
   - topic: a one-sentence summary of what is being debated
   - summary: controversy summary (academic review style, objectively present all viewpoints without taking sides, can be directly written into the "Research Controversies" section)
   - condition_analysis: experimental condition difference analysis (how differences in sample size, experimental model, treatment, time point, measurement method, etc. may lead to different conclusions)
   - sides: list of viewpoints from all parties, each containing side (e.g., "Viewpoint A"/"Viewpoint B"), evidence_ids (list of evidence IDs supporting this viewpoint), claim (core claim of this viewpoint)

Output strictly in JSON array format:
[
  {
    "topic": "Controversy topic",
    "summary": "Controversy summary text...",
    "condition_analysis": "Experimental condition difference analysis...",
    "sides": [
      {"side": "Viewpoint A", "evidence_ids": ["ev_001"], "claim": "Core claim A"},
      {"side": "Viewpoint B", "evidence_ids": ["ev_003"], "claim": "Core claim B"}
    ]
  }
]
Output only JSON, no other text. If contradictory pairs are unrelated, each pair becomes a separate controversy point."""


class ConflictDetector:
    """冲突识别 Agent：基于 contradicts 关系汇总争议点，生成争议小结。"""

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLMClient 实例（为 None 时用规则版：每个矛盾对单独成为冲突点）
        """
        self.llm = llm_client

    def detect(
        self,
        evidence_cards: list[EvidenceCard],
        relations: list[EvidenceRelation],
        language: str = "en",
    ) -> list[Conflict]:
        """
        从证据卡片和关系列表中识别冲突点。

        V25.5: 区分真正矛盾（true_controversy）和条件差异型（condition_difference），
        两类都会返回，conflict_type 字段区分，generate_controversy_section 会分别生成两个章节。
        V25.9: 支持 language 参数（默认英文）。

        Args:
            evidence_cards: 证据卡片列表
            relations: 关系列表（包含所有类型，内部自动筛选 contradicts）
            language: 输出语言，"en"（默认）或 "zh"

        Returns:
            Conflict 列表（含真正矛盾和条件差异型）
        """
        # 筛选矛盾关系
        all_contradictions = [r for r in relations if r.relation_type == RelationType.CONTRADICTS]
        if not all_contradictions:
            return []

        # V25.5: 分组——真正矛盾 vs 条件差异型
        true_contradictions = [r for r in all_contradictions if not r.condition_mismatch]
        condition_diff_contradictions = [r for r in all_contradictions if r.condition_mismatch]

        # 构建证据字典
        evidence_dict = {c.evidence_id: c for c in evidence_cards}

        all_conflicts: list[Conflict] = []

        # 处理真正矛盾
        if true_contradictions:
            if self.llm and self.llm.is_available():
                conflicts = self._llm_summarize(true_contradictions, evidence_dict, conflict_type="true_controversy", language=language)
                if conflicts:
                    all_conflicts.extend(conflicts)
            else:
                all_conflicts.extend(self._rule_based(true_contradictions, evidence_dict, conflict_type="true_controversy"))

        # 处理条件差异型
        if condition_diff_contradictions:
            if self.llm and self.llm.is_available():
                conflicts = self._llm_summarize_condition_diff(condition_diff_contradictions, evidence_dict, language=language)
                if conflicts:
                    all_conflicts.extend(conflicts)
            else:
                all_conflicts.extend(self._rule_based(condition_diff_contradictions, evidence_dict, conflict_type="condition_difference"))

        return all_conflicts

    def generate_controversy_section(self, conflicts: list[Conflict]) -> str:
        """
        根据冲突列表生成综述中的争议相关章节。

        V25.5: 生成两个章节：
        1. "研究争议与不一致"——真正矛盾（条件可比，结论相反）
        2. "不同实验条件下的结果差异"——条件差异型（结论不同但实验条件明显不同，客观陈述）

        如果没有冲突，返回空字符串。
        """
        if not conflicts:
            return ""

        # 分组
        true_controversies = [c for c in conflicts if c.conflict_type == "true_controversy"]
        condition_differences = [c for c in conflicts if c.conflict_type == "condition_difference"]

        lines = []

        # 章节1：真正矛盾
        if true_controversies:
            lines.append("## 研究争议与不一致\n")
            for i, conflict in enumerate(true_controversies, 1):
                lines.append(f"### {i}. {conflict.topic}\n")
                lines.append(f"{conflict.summary}\n")
                if conflict.condition_analysis:
                    lines.append(f"**实验条件差异分析**：{conflict.condition_analysis}\n")
                # 各方观点
                if conflict.sides:
                    lines.append("**各方观点**：\n")
                    for side in conflict.sides:
                        eids = ", ".join(f"[{eid}]" for eid in side.get("evidence_ids", []))
                        lines.append(f"- {side.get('side', '观点')}：{side.get('claim', '')} {eids}\n")
                lines.append("")

        # 章节2：条件差异型
        if condition_differences:
            lines.append("## 不同实验条件下的结果差异\n")
            lines.append("以下结果差异主要源于实验条件的不同（如突变类型、细胞类型、测量指标、刺激条件等），并非真正的学术争议。\n")
            for i, conflict in enumerate(condition_differences, 1):
                lines.append(f"### {i}. {conflict.topic}\n")
                lines.append(f"{conflict.summary}\n")
                if conflict.condition_analysis:
                    lines.append(f"**条件差异分析**：{conflict.condition_analysis}\n")
                # 各方条件和结论
                if conflict.sides:
                    lines.append("**各条件下的结果**：\n")
                    for side in conflict.sides:
                        eids = ", ".join(f"[{eid}]" for eid in side.get("evidence_ids", []))
                        lines.append(f"- {side.get('side', '条件')}：{side.get('claim', '')} {eids}\n")
                lines.append("")

        return "\n".join(lines)

    # ──────────────────────────────────────────
    # LLM 汇总
    # ──────────────────────────────────────────

    def _llm_summarize(
        self,
        contradictions: list[EvidenceRelation],
        evidence_dict: dict[str, EvidenceCard],
        conflict_type: str = "true_controversy",
        language: str = "en",
    ) -> list[Conflict]:
        """用 LLM 将矛盾关系汇总为结构化争议点。V25.9: 支持 language 参数。"""
        # 构建矛盾对描述
        pair_descriptions = []
        for idx, rel in enumerate(contradictions):
            src = evidence_dict.get(rel.source_evidence_id)
            tgt = evidence_dict.get(rel.target_evidence_id)
            if not src or not tgt:
                continue

            # V25.9: 按语言选择标签
            if language.lower() == "en":
                pair_descriptions.append(
                    f"--- Contradiction pair {idx} ---\n"
                    f"[Evidence A] ID={src.evidence_id}, Paper={src.paper_id[:30]}\n"
                    f"  Type={src.evidence_type.value}, Content={src.content[:200]}\n"
                    f"  Conditions: Model={src.model_system or 'unknown'}, Sample={src.sample_size or 'unknown'}, "
                    f"Treatment={src.treatment or 'unknown'}, Time={src.time_point or 'unknown'}\n"
                    f"  Fine-grained: Mutation={src.mutation_type or 'unknown'}, Cell={src.cell_type or 'unknown'}, "
                    f"Measurement={src.measurement or 'unknown'}, Stimulus={src.stimulus or 'unknown'}\n"
                    f"[Evidence B] ID={tgt.evidence_id}, Paper={tgt.paper_id[:30]}\n"
                    f"  Type={tgt.evidence_type.value}, Content={tgt.content[:200]}\n"
                    f"  Conditions: Model={tgt.model_system or 'unknown'}, Sample={tgt.sample_size or 'unknown'}, "
                    f"Treatment={tgt.treatment or 'unknown'}, Time={tgt.time_point or 'unknown'}\n"
                    f"  Fine-grained: Mutation={tgt.mutation_type or 'unknown'}, Cell={tgt.cell_type or 'unknown'}, "
                    f"Measurement={tgt.measurement or 'unknown'}, Stimulus={tgt.stimulus or 'unknown'}\n"
                    f"[Relation reason] {rel.explanation[:150]}\n"
                    f"[Condition diff] {rel.condition_diff[:150]}"
                )
            else:
                pair_descriptions.append(
                    f"--- 矛盾对 {idx} ---\n"
                    f"[证据A] ID={src.evidence_id}, 论文={src.paper_id[:30]}\n"
                    f"  类型={src.evidence_type.value}, 内容={src.content[:200]}\n"
                    f"  实验条件: 模型={src.model_system or '未知'}, 样本={src.sample_size or '未知'}, "
                    f"处理={src.treatment or '未知'}, 时间点={src.time_point or '未知'}\n"
                    f"  细粒度条件: 突变类型={src.mutation_type or '未知'}, 细胞类型={src.cell_type or '未知'}, "
                    f"测量指标={src.measurement or '未知'}, 刺激条件={src.stimulus or '未知'}\n"
                    f"[证据B] ID={tgt.evidence_id}, 论文={tgt.paper_id[:30]}\n"
                    f"  类型={tgt.evidence_type.value}, 内容={tgt.content[:200]}\n"
                    f"  实验条件: 模型={tgt.model_system or '未知'}, 样本={tgt.sample_size or '未知'}, "
                    f"处理={tgt.treatment or '未知'}, 时间点={tgt.time_point or '未知'}\n"
                    f"  细粒度条件: 突变类型={tgt.mutation_type or '未知'}, 细胞类型={tgt.cell_type or '未知'}, "
                    f"测量指标={tgt.measurement or '未知'}, 刺激条件={tgt.stimulus or '未知'}\n"
                    f"[关系判定理由] {rel.explanation[:150]}\n"
                    f"[条件差异] {rel.condition_diff[:150]}"
                )

        if not pair_descriptions:
            return []

        # V25.9: 按语言选择 system prompt 和 user prompt 前缀
        sys_prompt = SYSTEM_PROMPT_EN if language.lower() == "en" else SYSTEM_PROMPT
        if language.lower() == "en":
            user_prompt = "The following are contradictory evidence pairs from the literature. Please synthesize them into structured controversy points:\n\n" + "\n\n".join(pair_descriptions)
        else:
            user_prompt = "以下是文献间的矛盾证据对，请汇总为结构化争议点：\n\n" + "\n\n".join(pair_descriptions)

        try:
            results = self.llm.chat_json(sys_prompt, user_prompt)
            if not isinstance(results, list):
                return []

            conflicts = []
            for i, item in enumerate(results):
                if not isinstance(item, dict):
                    continue
                topic = item.get("topic", "").strip()
                summary = item.get("summary", "").strip()
                if not topic or not summary:
                    continue

                # 收集涉及的证据ID
                all_evidence_ids = set()
                sides = item.get("sides", [])
                for side in sides:
                    for eid in side.get("evidence_ids", []):
                        if eid in evidence_dict:
                            all_evidence_ids.add(eid)

                # 如果 sides 里没有收集到，从矛盾对中补
                if not all_evidence_ids and i < len(contradictions):
                    rel = contradictions[i]
                    all_evidence_ids.add(rel.source_evidence_id)
                    all_evidence_ids.add(rel.target_evidence_id)

                paper_ids = list({
                    evidence_dict[eid].paper_id
                    for eid in all_evidence_ids
                    if eid in evidence_dict
                })

                conflicts.append(Conflict(
                    conflict_id=f"conflict_{i:03d}",
                    topic=topic,
                    evidence_ids=list(all_evidence_ids),
                    paper_ids=paper_ids,
                    summary=summary,
                    condition_analysis=item.get("condition_analysis", ""),
                    sides=sides if isinstance(sides, list) else [],
                    conflict_type=conflict_type,
                ))

            return conflicts

        except Exception:
            return []

    # ──────────────────────────────────────────
    # V25.5: 条件差异型 LLM 汇总
    # ──────────────────────────────────────────

    def _llm_summarize_condition_diff(
        self,
        condition_diff_relations: list[EvidenceRelation],
        evidence_dict: dict[str, EvidenceCard],
        language: str = "en",
    ) -> list[Conflict]:
        """V25.5: 用 LLM 将条件差异型矛盾汇总为"不同实验条件下的结果差异"条目。V25.9: 支持 language 参数。

        与真正矛盾不同，条件差异型的重点不是"谁对谁错"，而是：
        1. 客观陈述双方的实验条件和结论
        2. 分析条件差异如何导致结果不同
        3. 不使用"争议""矛盾""不一致"等词汇
        """
        # 构建条件差异对描述
        pair_descriptions = []
        for idx, rel in enumerate(condition_diff_relations):
            src = evidence_dict.get(rel.source_evidence_id)
            tgt = evidence_dict.get(rel.target_evidence_id)
            if not src or not tgt:
                continue

            # V25.9: 按语言选择标签
            if language.lower() == "en":
                pair_descriptions.append(
                    f"--- Condition diff pair {idx} ---\n"
                    f"[Mismatch reason] {rel.mismatch_reason or 'unknown'}\n"
                    f"[Evidence A] ID={src.evidence_id}, Paper={src.paper_id[:30]}\n"
                    f"  Content={src.content[:200]}\n"
                    f"  Conditions: Mutation={src.mutation_type or 'unknown'}, Cell={src.cell_type or 'unknown'}, "
                    f"Measurement={src.measurement or 'unknown'}, Stimulus={src.stimulus or 'unknown'}, "
                    f"Model={src.model_system or 'unknown'}, Treatment={src.treatment or 'unknown'}, Time={src.time_point or 'unknown'}\n"
                    f"[Evidence B] ID={tgt.evidence_id}, Paper={tgt.paper_id[:30]}\n"
                    f"  Content={tgt.content[:200]}\n"
                    f"  Conditions: Mutation={tgt.mutation_type or 'unknown'}, Cell={tgt.cell_type or 'unknown'}, "
                    f"Measurement={tgt.measurement or 'unknown'}, Stimulus={tgt.stimulus or 'unknown'}, "
                    f"Model={tgt.model_system or 'unknown'}, Treatment={tgt.treatment or 'unknown'}, Time={tgt.time_point or 'unknown'}"
                )
            else:
                pair_descriptions.append(
                    f"--- 条件差异对 {idx} ---\n"
                    f"[条件差异原因] {rel.mismatch_reason or '未知'}\n"
                    f"[证据A] ID={src.evidence_id}, 论文={src.paper_id[:30]}\n"
                    f"  内容={src.content[:200]}\n"
                    f"  实验条件: 突变类型={src.mutation_type or '未知'}, 细胞类型={src.cell_type or '未知'}, "
                    f"测量指标={src.measurement or '未知'}, 刺激条件={src.stimulus or '未知'}, "
                    f"模型={src.model_system or '未知'}, 处理={src.treatment or '未知'}, 时间点={src.time_point or '未知'}\n"
                    f"[证据B] ID={tgt.evidence_id}, 论文={tgt.paper_id[:30]}\n"
                    f"  内容={tgt.content[:200]}\n"
                    f"  实验条件: 突变类型={tgt.mutation_type or '未知'}, 细胞类型={tgt.cell_type or '未知'}, "
                    f"测量指标={tgt.measurement or '未知'}, 刺激条件={tgt.stimulus or '未知'}, "
                    f"模型={tgt.model_system or '未知'}, 处理={tgt.treatment or '未知'}, 时间点={tgt.time_point or '未知'}"
                )

        if not pair_descriptions:
            return []

        # V25.9: 按语言选择 system prompt
        if language.lower() == "en":
            system_prompt = """You are an expert scientific review writer. Your task is to analyze cases where "results differ under different experimental conditions" and synthesize them into structured condition-difference entries.

Important: These are NOT "controversies" or "contradictions", but result differences caused by different experimental conditions. Your task is to:
1. Cluster related condition-difference pairs (those discussing the same indicator/pathway should be grouped together)
2. For each entry, generate:
   - topic: a one-sentence summary of "on what issue results differ under different conditions"
   - summary: objective statement (academic review style, do not use words like "controversy", "contradiction", "inconsistency"; instead say "under condition A, X was observed; under condition B, Y was observed")
   - condition_analysis: detailed analysis of how experimental condition differences lead to different results (mutation type/cell type/measurement endpoint/stimulus condition, etc.)
   - sides: list of conditions and conclusions from each party, each containing side (e.g., "Condition A"/"Condition B"), evidence_ids, claim (conclusion under that condition)

Output strictly in JSON array format, only JSON, no other text."""
            user_prompt = "The following are cases where results differ under different experimental conditions. Please synthesize them into structured condition-difference entries:\n\n" + "\n\n".join(pair_descriptions)
        else:
            system_prompt = """你是一位科研综述写作专家。你的任务是分析"不同实验条件下结果不同"的案例，汇总为结构化的条件差异条目。

重要：这些不是"争议"或"矛盾"，而是因为实验条件不同导致的结果差异。你的任务是：
1. 将相关的条件差异对聚类（讨论同一指标/同一通路的归为一组）
2. 为每个条目生成：
   - topic：一句话概括"在什么问题上，不同条件下结果不同"
   - summary：客观陈述（学术综述风格，不使用"争议""矛盾""不一致"等词汇，而是说"在A条件下观察到X，在B条件下观察到Y"）
   - condition_analysis：详细分析实验条件差异如何导致结果不同（突变类型/细胞类型/测量指标/刺激条件等）
   - sides：各方的条件和结论列表，每方包含 side（如"条件A"/"条件B"）、evidence_ids、claim（该条件下的结论）

输出严格 JSON 数组格式，只输出 JSON，不要任何其他文字。"""
            user_prompt = "以下是不同实验条件下结果不同的案例，请汇总为结构化条件差异条目：\n\n" + "\n\n".join(pair_descriptions)

        try:
            results = self.llm.chat_json(system_prompt, user_prompt)
            if not isinstance(results, list):
                return []

            conflicts = []
            for i, item in enumerate(results):
                if not isinstance(item, dict):
                    continue
                topic = item.get("topic", "").strip()
                summary = item.get("summary", "").strip()
                if not topic or not summary:
                    continue

                # 收集涉及的证据ID
                all_evidence_ids = set()
                sides = item.get("sides", [])
                for side in sides:
                    for eid in side.get("evidence_ids", []):
                        if eid in evidence_dict:
                            all_evidence_ids.add(eid)

                # 如果 sides 里没有收集到，从条件差异对中补
                if not all_evidence_ids and i < len(condition_diff_relations):
                    rel = condition_diff_relations[i]
                    all_evidence_ids.add(rel.source_evidence_id)
                    all_evidence_ids.add(rel.target_evidence_id)

                paper_ids = list({
                    evidence_dict[eid].paper_id
                    for eid in all_evidence_ids
                    if eid in evidence_dict
                })

                conflicts.append(Conflict(
                    conflict_id=f"conddiff_{i:03d}",
                    topic=topic,
                    evidence_ids=list(all_evidence_ids),
                    paper_ids=paper_ids,
                    summary=summary,
                    condition_analysis=item.get("condition_analysis", ""),
                    sides=sides if isinstance(sides, list) else [],
                    conflict_type="condition_difference",
                ))

            return conflicts

        except Exception:
            return []

    # ──────────────────────────────────────────
    # 规则版 fallback
    # ──────────────────────────────────────────

    def _rule_based(
        self,
        contradictions: list[EvidenceRelation],
        evidence_dict: dict[str, EvidenceCard],
        conflict_type: str = "true_controversy",
    ) -> list[Conflict]:
        """规则版：每个矛盾对单独成为一个冲突点，不做聚类。"""
        conflicts = []
        for i, rel in enumerate(contradictions):
            src = evidence_dict.get(rel.source_evidence_id)
            tgt = evidence_dict.get(rel.target_evidence_id)
            if not src or not tgt:
                continue

            if conflict_type == "condition_difference":
                # 条件差异型：客观陈述，不使用"争议""矛盾"词汇
                topic = f"{src.content[:25]}...（{src.mutation_type or '未知'}/{src.measurement or '未知'}）vs {tgt.content[:25]}...（{tgt.mutation_type or '未知'}/{tgt.measurement or '未知'}）"
                summary = (
                    f"在不同实验条件下观察到不同结果。"
                    f"文献{src.paper_id[:20]}在{src.mutation_type or '未知'}背景、{src.cell_type or '未知'}中、"
                    f"测量{src.measurement or '未知'}时发现：{src.content[:80]}。"
                    f"而文献{tgt.paper_id[:20]}在{tgt.mutation_type or '未知'}背景、{tgt.cell_type or '未知'}中、"
                    f"测量{tgt.measurement or '未知'}时发现：{tgt.content[:80]}。"
                    f"两者结果差异可能源于实验条件不同。"
                )
                condition_analysis = rel.mismatch_reason or (
                    f"实验条件存在明显差异：文献{src.paper_id[:20]}使用{src.mutation_type or '未知'}突变、"
                    f"{src.cell_type or '未知'}、测量{src.measurement or '未知'}、{src.stimulus or '未知'}；"
                    f"文献{tgt.paper_id[:20]}使用{tgt.mutation_type or '未知'}突变、"
                    f"{tgt.cell_type or '未知'}、测量{tgt.measurement or '未知'}、{tgt.stimulus or '未知'}。"
                    f"这些条件差异可能导致结果不同。"
                )
                side_a_label = f"条件A（{src.mutation_type or '未知'}/{src.measurement or '未知'}）"
                side_b_label = f"条件B（{tgt.mutation_type or '未知'}/{tgt.measurement or '未知'}）"
            else:
                # 真正矛盾
                topic = f"{src.content[:30]}... vs {tgt.content[:30]}..."
                summary = (
                    f"研究{src.evidence_type.value}与{tgt.evidence_type.value}之间存在不一致。"
                    f"文献{src.paper_id[:20]}认为：{src.content[:100]}。"
                    f"而文献{tgt.paper_id[:20]}则提出：{tgt.content[:100]}。"
                    f"两者结论存在差异，需进一步验证。"
                )
                condition_analysis = rel.condition_diff or (
                    f"实验条件可能存在差异：文献{src.paper_id[:20]}使用{src.model_system or '未知模型'}，"
                    f"样本量{src.sample_size or '未知'}；文献{tgt.paper_id[:20]}使用{tgt.model_system or '未知模型'}，"
                    f"样本量{tgt.sample_size or '未知'}。这些差异可能导致结论不同。"
                )
                side_a_label = "观点A"
                side_b_label = "观点B"

            conflicts.append(Conflict(
                conflict_id=f"conflict_{i:03d}" if conflict_type == "true_controversy" else f"conddiff_{i:03d}",
                topic=topic,
                evidence_ids=[src.evidence_id, tgt.evidence_id],
                paper_ids=[src.paper_id, tgt.paper_id],
                summary=summary,
                condition_analysis=condition_analysis,
                sides=[
                    {"side": side_a_label, "evidence_ids": [src.evidence_id], "claim": src.content[:100]},
                    {"side": side_b_label, "evidence_ids": [tgt.evidence_id], "claim": tgt.content[:100]},
                ],
                conflict_type=conflict_type,
            ))

        return conflicts


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("⚔️  Conflict Detector Test (V25.3)")
    print("=" * 60)

    # 构造测试证据卡片
    test_cards = [
        EvidenceCard(
            evidence_id="ev_001", paper_id="paper_A", para_id="p1",
            evidence_type="fact",
            content="STAT1 knockout mice are highly susceptible to viral infections.",
            model_system="C57BL/6小鼠", sample_size="n=20",
            treatment="VSV病毒感染", time_point="7天",
        ),
        EvidenceCard(
            evidence_id="ev_002", paper_id="paper_B", para_id="p1",
            evidence_type="claim",
            content="STAT1 is not essential for antiviral immunity in lung epithelial cells.",
            model_system="人肺上皮细胞系", sample_size="n=3",
            treatment="流感病毒感染", time_point="24小时",
        ),
        EvidenceCard(
            evidence_id="ev_003", paper_id="paper_C", para_id="p1",
            evidence_type="fact",
            content="STAT1 deficiency leads to increased susceptibility to mycobacterial infections.",
            model_system="人类患者", sample_size="n=9",
        ),
    ]

    # 构造矛盾关系
    test_relations = [
        EvidenceRelation(
            relation_id="rel_001",
            source_evidence_id="ev_001",
            target_evidence_id="ev_002",
            relation_type=RelationType.CONTRADICTS,
            confidence=0.85,
            explanation="一方认为STAT1对抗病毒免疫至关重要，另一方认为在上皮细胞中非必需",
            condition_diff="ev_001使用小鼠整体模型+VSV病毒+7天时间点，ev_002使用人细胞系+流感病毒+24小时，模型和病毒种类不同",
        ),
        EvidenceRelation(
            relation_id="rel_002",
            source_evidence_id="ev_001",
            target_evidence_id="ev_003",
            relation_type=RelationType.SUPPORTS,
            confidence=0.9,
            explanation="两者都表明STAT1缺陷导致感染易感性增加",
        ),
    ]

    # 测试规则版（无 LLM）
    detector = ConflictDetector(llm_client=None)
    conflicts = detector.detect(test_cards, test_relations)

    print(f"\n矛盾关系数: {len([r for r in test_relations if r.relation_type == RelationType.CONTRADICTS])}")
    print(f"识别到冲突点数: {len(conflicts)}")

    for c in conflicts:
        print(f"\n  [{c.conflict_id}] {c.topic}")
        print(f"    涉及证据: {c.evidence_ids}")
        print(f"    涉及论文: {c.paper_ids}")
        print(f"    小结: {c.summary[:80]}...")
        print(f"    条件分析: {c.condition_analysis[:80]}...")
        for side in c.sides:
            print(f"    {side['side']}: {side['claim'][:50]}...")

    # 测试争议章节生成
    print("\n--- 生成的研究争议章节 ---")
    section = detector.generate_controversy_section(conflicts)
    print(section[:500] if section else "(无冲突)")

    print("\n✅ 冲突识别测试完成（规则版）。")
    print("   LLM 版需要 Ollama 服务运行，可自动聚类相关矛盾对并生成更学术的争议小结。")
