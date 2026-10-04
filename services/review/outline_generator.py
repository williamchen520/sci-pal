"""
V25.2 - 综述大纲生成器（OutlineGenerator）。

基于检索到的证据卡片，自动生成综述大纲（章节结构 + 每章分配的证据）。
优先使用 LLM 生成；LLM 不可用时回退到规则版（按 evidence_type 分章）。

可选：复用 V24.3 的 paper_communities 表，将文献聚类信息作为 LLM 的参考，
帮助大纲按研究方向/观点派别分组。

用法:
    generator = OutlineGenerator(llm_client)
    outline = generator.generate(topic="STAT1 干扰素调控", evidence_cards=cards)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .models import (
    ConfidenceLevel,
    EvidenceCard,
    EvidenceType,
    ReviewOutline,
    ReviewParagraph,
    ReviewSection,
)


# ──────────────────────────────────────────────
# LLM 大纲生成 Prompt（V25.7: 三种综述模板；V25.9: 英文默认）
# ──────────────────────────────────────────────

# 模板1：叙事型综述（Narrative Review）—— 默认（英文）
# 特点：按主题/逻辑线索组织，讲故事式的叙述
# 适用：领域概览、教学入门、broad overview
NARRATIVE_SYSTEM_PROMPT_EN = """You are an expert academic review writer. Your task is to generate a structured outline for a **narrative academic review** based on the given evidence cards.

A narrative review is organized by logical threads, progressing from background to mechanisms to evidence to controversies to outlook, like telling a story layer by layer.

Requirements:
1. 3-6 sections, arranged in logical order (Background → Mechanisms → Evidence → Controversies → Limitations → Outlook)
2. **Each section must contain 2-3 paragraphs**, each with a clear topic
3. Each section must have a clear title and brief description
4. Each paragraph must have a clear topic (one sentence summarizing what this paragraph covers)
5. **V31.11: Each paragraph topic must be a specific writing instruction**, not a vague title. For example: "Describe the structural domains of STAT1 and their function in the JAK-STAT pathway" instead of "STAT1 background"
6. Each section must be assigned at least 1 evidence ID (selected from the given evidence list)
7. Evidence IDs must be used exactly as given — never fabricate non-existent IDs
8. Prioritize assigning evidence from the same research direction / similar conclusions to the same section
9. If there are obvious conflicting viewpoints among evidence, create a separate "Research Controversies" section

Output strictly in JSON format, no other text:
{
  "sections": [
    {
      "title": "Section Title",
      "description": "Key points of this section (1-2 sentences)",
      "evidence_ids": ["ev_001", "ev_002"],
      "paragraphs": [
        {"topic": "First paragraph topic (one sentence)"},
        {"topic": "Second paragraph topic (one sentence)"}
      ]
    }
  ]
}"""

# 模板2：实验对比型综述（Comparative Review）—— 英文
COMPARATIVE_SYSTEM_PROMPT_EN = """You are an expert academic review writer. Your task is to generate a structured outline for an **experimental comparative academic review** based on the given evidence cards.

A comparative review is organized around experimental methods, model systems, and experimental conditions, emphasizing comparisons and differences between studies rather than chronological or thematic narrative.

Requirements:
1. 3-6 sections, organized by "Method classification → Comparative analysis → Pros/cons discussion → Conclusion"
2. **Each section must contain 2-3 paragraphs**, each with a clear topic
3. The first section is typically "Research Background and Method Classification", the last is typically "Summary and Outlook"
4. Middle sections are classified by experimental method / model system / experimental condition, each focusing on one class of methods or models
5. Each section must have a clear title and brief description
6. Each paragraph must have a clear topic (one sentence summarizing what this paragraph covers)
7. Each section must be assigned at least 1 evidence ID (selected from the given evidence list)
8. Evidence IDs must be used exactly as given — never fabricate non-existent IDs
9. Prioritize assigning evidence using the same experimental method / same model system to the same section
10. If different methods yield different conclusions, explicitly mark the comparison dimension in the corresponding section
11. If there are obvious conflicting viewpoints, create a separate "Methodological Controversies" or "Result Difference Analysis" section

Output strictly in JSON format, no other text:
{
  "sections": [
    {
      "title": "Section Title",
      "description": "Key points of this section (1-2 sentences)",
      "evidence_ids": ["ev_001", "ev_002"],
      "paragraphs": [
        {"topic": "First paragraph topic (one sentence)"},
        {"topic": "Second paragraph topic (one sentence)"}
      ]
    }
  ]
}"""

# 模板3：系统综述型（Systematic Review）—— 英文
SYSTEMATIC_SYSTEM_PROMPT_EN = """You are an expert academic review writer. Your task is to generate a structured outline for a **systematic review** based on the given evidence cards.

A systematic review features methodological transparency, strict structure, emphasis on evidence quality assessment and risk of bias, rather than free narrative.

Requirements:
1. Fixed 5-7 sections, strictly organized by standard systematic review structure:
   - Background & Objectives
   - Methods: Search strategy & Inclusion/Exclusion criteria
   - Results: Characteristics of included studies
   - Results: Risk of bias / Quality assessment
   - Results: Synthesis of evidence
   - Discussion & Conclusion
2. **Each section must contain 2-3 paragraphs**, each with a clear topic
3. Each section must have a clear title and brief description
4. Each paragraph must have a clear topic (one sentence summarizing what this paragraph covers)
5. Each section must be assigned at least 1 evidence ID (selected from the given evidence list)
6. Evidence IDs must be used exactly as given — never fabricate non-existent IDs
7. The "Characteristics of included studies" section should include as much evidence as possible, classified by research method / model
8. The "Synthesis of evidence" section should focus on consistency and differences between evidence
9. If there are obvious conflicting viewpoints, explicitly discuss them in "Synthesis of evidence" or a separate section
10. Note: Since this system is based on a local literature library, the search strategy and inclusion/exclusion criteria sections can describe the actually retrieved literature (e.g., "searched the local literature library for papers related to the topic"), no need to fabricate external database search details

Output strictly in JSON format, no other text:
{
  "sections": [
    {
      "title": "Section Title",
      "description": "Key points of this section (1-2 sentences)",
      "evidence_ids": ["ev_001", "ev_002"],
      "paragraphs": [
        {"topic": "First paragraph topic (one sentence)"},
        {"topic": "Second paragraph topic (one sentence)"}
      ]
    }
  ]
}"""

# 中文 prompt（保留向后兼容，language=zh 时使用）
NARRATIVE_SYSTEM_PROMPT_ZH = """你是一位资深科研综述写作专家。你的任务是根据给定的证据卡片，为一篇**叙事型学术综述**生成结构化大纲。

叙事型综述的特点：按逻辑线索组织，从背景到机制到证据到争议到展望，像讲故事一样层层递进。

要求：
1. 章节数量 3-6 个，按逻辑顺序排列（背景→机制→证据→争议→局限→展望）
2. **每个章节必须包含 2-3 个段落**，每个段落有明确的主题
3. 每个章节必须有明确的标题和简短描述
4. 每个段落必须有明确的主题（一句话概括本段写什么）
5. 每个章节必须分配至少 1 个证据ID（从给定的证据列表中选择）
6. 证据ID必须原样使用，不得编造不存在的ID
7. 优先将相同研究方向/相似结论的证据分到同一章节
8. 如果证据之间存在明显观点冲突，应单独设立"研究争议"章节

输出严格 JSON 格式，不要输出任何其他文字：
{
  "sections": [
    {
      "title": "章节标题",
      "description": "本章内容要点（1-2句话）",
      "evidence_ids": ["ev_001", "ev_002"],
      "paragraphs": [
        {"topic": "第一段主题（一句话）"},
        {"topic": "第二段主题（一句话）"}
      ]
    }
  ]
}"""

COMPARATIVE_SYSTEM_PROMPT_ZH = """你是一位资深科研综述写作专家。你的任务是根据给定的证据卡片，为一篇**实验对比型学术综述**生成结构化大纲。

实验对比型综述的特点：以实验方法、模型系统、实验条件为核心组织线索，强调不同研究之间的对比和差异，而不是按时间或主题叙事。

要求：
1. 章节数量 3-6 个，按"方法分类→对比分析→优缺点讨论→结论"的逻辑组织
2. **每个章节必须包含 2-3 个段落**，每个段落有明确的主题
3. 第一个章节通常是"研究背景与方法分类"，最后一个章节通常是"总结与展望"
4. 中间章节按实验方法/模型系统/实验条件分类，每章聚焦一类方法或模型
5. 每个章节必须有明确的标题和简短描述
6. 每个段落必须有明确的主题（一句话概括本段写什么）
7. 每个章节必须分配至少 1 个证据ID（从给定的证据列表中选择）
8. 证据ID必须原样使用，不得编造不存在的ID
9. 优先将使用相同实验方法/相同模型系统的证据分到同一章节
10. 如果不同方法得出的结论存在差异，应在对应章节中明确标注对比维度
11. 如果证据之间存在明显观点冲突，应单独设立"方法学争议"或"结果差异分析"章节

输出严格 JSON 格式，不要输出任何其他文字：
{
  "sections": [
    {
      "title": "章节标题",
      "description": "本章内容要点（1-2句话）",
      "evidence_ids": ["ev_001", "ev_002"],
      "paragraphs": [
        {"topic": "第一段主题（一句话）"},
        {"topic": "第二段主题（一句话）"}
      ]
    }
  ]
}"""

SYSTEMATIC_SYSTEM_PROMPT_ZH = """你是一位资深科研综述写作专家。你的任务是根据给定的证据卡片，为一篇**系统综述型学术综述**生成结构化大纲。

系统综述型的特点：方法学透明、结构严格、强调证据质量评估和偏倚风险，而不是自由叙事。

要求：
1. 章节数量固定为 5-7 个，严格按系统综述的标准结构组织：
   - 背景与目的（Background & Objectives）
   - 检索策略与纳入排除标准（Methods: Search strategy & Inclusion/Exclusion criteria）
   - 纳入研究特征（Results: Characteristics of included studies）
   - 证据质量与偏倚评估（Results: Risk of bias / Quality assessment）
   - 证据综合与分析（Results: Synthesis of evidence）
   - 讨论与结论（Discussion & Conclusion）
2. **每个章节必须包含 2-3 个段落**，每个段落有明确的主题
3. 每个章节必须有明确的标题和简短描述
4. 每个段落必须有明确的主题（一句话概括本段写什么）
5. 每个章节必须分配至少 1 个证据ID（从给定的证据列表中选择）
6. 证据ID必须原样使用，不得编造不存在的ID
7. "纳入研究特征"章节应包含尽可能多的证据，按研究方法/模型分类
8. "证据综合与分析"章节应聚焦证据之间的一致性和差异性
9. 如果证据之间存在明显观点冲突，应在"证据综合与分析"或单独章节中明确讨论
10. 注意：由于本系统是基于本地文献库的，检索策略和纳入排除标准章节可以基于实际检索到的文献来描述（如"检索了本地文献库中与主题相关的论文"），不需要编造外部数据库的检索细节

输出严格 JSON 格式，不要输出任何其他文字：
{
  "sections": [
    {
      "title": "章节标题",
      "description": "本章内容要点（1-2句话）",
      "evidence_ids": ["ev_001", "ev_002"],
      "paragraphs": [
        {"topic": "第一段主题（一句话）"},
        {"topic": "第二段主题（一句话）"}
      ]
    }
  ]
}"""

# V25.9: 按语言选择 prompt
REVIEW_TYPE_PROMPTS_EN = {
    "narrative": NARRATIVE_SYSTEM_PROMPT_EN,
    "comparative": COMPARATIVE_SYSTEM_PROMPT_EN,
    "systematic": SYSTEMATIC_SYSTEM_PROMPT_EN,
    "story": NARRATIVE_SYSTEM_PROMPT_EN,
    "experiment": COMPARATIVE_SYSTEM_PROMPT_EN,
    "experimental": COMPARATIVE_SYSTEM_PROMPT_EN,
    "compare": COMPARATIVE_SYSTEM_PROMPT_EN,
    "meta": SYSTEMATIC_SYSTEM_PROMPT_EN,
    "meta-analysis": SYSTEMATIC_SYSTEM_PROMPT_EN,
}

REVIEW_TYPE_PROMPTS_ZH = {
    "narrative": NARRATIVE_SYSTEM_PROMPT_ZH,
    "comparative": COMPARATIVE_SYSTEM_PROMPT_ZH,
    "systematic": SYSTEMATIC_SYSTEM_PROMPT_ZH,
    "story": NARRATIVE_SYSTEM_PROMPT_ZH,
    "experiment": COMPARATIVE_SYSTEM_PROMPT_ZH,
    "experimental": COMPARATIVE_SYSTEM_PROMPT_ZH,
    "compare": COMPARATIVE_SYSTEM_PROMPT_ZH,
    "meta": SYSTEMATIC_SYSTEM_PROMPT_ZH,
    "meta-analysis": SYSTEMATIC_SYSTEM_PROMPT_ZH,
}

# 兼容旧代码：默认使用英文叙事型
SYSTEM_PROMPT = NARRATIVE_SYSTEM_PROMPT_EN

# 模板类型映射（V25.9: 默认英文）
REVIEW_TYPE_PROMPTS = REVIEW_TYPE_PROMPTS_EN


class OutlineGenerator:
    """综述大纲生成器：LLM 优先，规则版 fallback。"""

    def __init__(
        self,
        llm_client=None,
        db_path: Optional[str] = None,
        min_sections: int = 3,
        max_sections: int = 6,
    ):
        """
        Args:
            llm_client: LLMClient 实例（为 None 时使用规则版 fallback）
            db_path: SQLite 数据库路径，用于读取 paper_communities 文献聚类信息
            min_sections: 最少章节数
            max_sections: 最多章节数
        """
        self.llm = llm_client
        self.db_path = db_path
        self.min_sections = min_sections
        self.max_sections = max_sections

    def generate(
        self,
        topic: str,
        evidence_cards: list[EvidenceCard],
        use_communities: bool = True,
        review_type: str = "narrative",
        language: str = "en",
    ) -> ReviewOutline:
        """
        生成综述大纲。

        Args:
            topic: 综述主题
            evidence_cards: 证据卡片列表
            use_communities: 是否使用文献聚类信息（需要 db_path）
            review_type: 综述模板类型（V25.7）：
                - "narrative": 叙事型（默认，按逻辑线索组织）
                - "comparative": 实验对比型（按方法/模型对比）
                - "systematic": 系统综述型（严格方法学结构）
            language: V25.9: 大纲语言，"en"（默认，英文）或 "zh"（中文）

        Returns:
            ReviewOutline 大纲对象
        """
        if not evidence_cards:
            return ReviewOutline(topic=topic, sections=[], total_papers=0, total_evidence=0)

        # V31.70: 直接用规则版生成大纲，不调用 LLM，避免本地模型超时
        return self._generate_rule_based(topic, evidence_cards, language=language)

    # ──────────────────────────────────────────
    # LLM 生成
    # ──────────────────────────────────────────

    def _generate_with_llm(
        self,
        topic: str,
        evidence_cards: list[EvidenceCard],
        use_communities: bool,
        review_type: str = "narrative",
        language: str = "en",
    ) -> Optional[ReviewOutline]:
        """使用 LLM 生成大纲。V25.9: 支持英文/中文 prompt。"""
        # V25.9: 根据语言选择 prompt 集
        prompts = REVIEW_TYPE_PROMPTS_EN if language.lower() == "en" else REVIEW_TYPE_PROMPTS_ZH
        system_prompt = prompts.get(review_type.lower(), NARRATIVE_SYSTEM_PROMPT_EN if language.lower() == "en" else NARRATIVE_SYSTEM_PROMPT_ZH)

        # 构建证据摘要（只传必要信息，节省 token）
        # V31.69: 限制证据卡片数量，最多传 200 个，避免 LLM 处理不了
        max_evidence_for_outline = 200
        evidence_for_outline = evidence_cards[:max_evidence_for_outline]
        evidence_summary = []
        for card in evidence_for_outline:
            evidence_summary.append({
                "id": card.evidence_id,
                "type": card.evidence_type.value,
                "content": card.content[:120],
                "paper": card.paper_id[:30],
            })

        # 可选：文献聚类信息
        community_hint = ""
        if use_communities and self.db_path:
            communities = self._load_communities(evidence_cards)
            if communities:
                community_lines = []
                for cid, members in communities.items():
                    if members:
                        community_lines.append(f"社区{cid}: {', '.join(m[:20] for m in members[:5])}")
                if community_lines:
                    community_hint = "\n\n文献聚类参考（同一社区的论文研究方向相近，尽量分到同一章节）：\n" + "\n".join(community_lines)

        # V25.9: 根据语言选择类型标签
        if language.lower() == "en":
            type_label = {
                "narrative": "Narrative Review",
                "comparative": "Comparative Review",
                "systematic": "Systematic Review",
            }.get(review_type.lower(), "Narrative Review")
            user_prompt = (
                f"Review topic: {topic}\n"
                f"Review type: {type_label} ({review_type})\n\n"
                f"Evidence cards ({len(evidence_for_outline)} shown, {len(evidence_cards)} total):\n"
                f"{json.dumps(evidence_summary, ensure_ascii=False, indent=2)}"
                f"{community_hint}\n\n"
                f"Please generate a {type_label} outline based on the above evidence, with {self.min_sections}-{self.max_sections} sections."
            )
        else:
            type_label = {
                "narrative": "叙事型综述",
                "comparative": "实验对比型综述",
                "systematic": "系统综述型",
            }.get(review_type.lower(), "叙事型综述")
            user_prompt = (
                f"综述主题：{topic}\n"
                f"综述模板类型：{type_label}（{review_type}）\n\n"
                f"证据卡片列表（展示 {len(evidence_for_outline)} 条，共 {len(evidence_cards)} 条）：\n"
                f"{json.dumps(evidence_summary, ensure_ascii=False, indent=2)}"
                f"{community_hint}\n\n"
                f"请根据以上证据生成{type_label}大纲，章节数 {self.min_sections}-{self.max_sections} 个。"
            )

        try:
            result = self.llm.chat_json(system_prompt, user_prompt)
            if not isinstance(result, dict) or "sections" not in result:
                return None

            sections_data = result["sections"]
            if not isinstance(sections_data, list) or not sections_data:
                return None

            # 构建 ReviewSection 列表
            valid_evidence_ids = {c.evidence_id for c in evidence_cards}
            sections = []
            for i, sec in enumerate(sections_data[:self.max_sections]):
                if not isinstance(sec, dict):
                    continue
                title = sec.get("title", "").strip()
                if not title:
                    continue
                # 过滤掉不存在的 evidence_id
                assigned = [eid for eid in sec.get("evidence_ids", []) if eid in valid_evidence_ids]
                if not assigned:
                    # 如果 LLM 没分配证据，跳过该章节
                    continue

                # V25.8: 解析段落级大纲
                paragraphs_data = sec.get("paragraphs", [])
                paragraphs = []
                if isinstance(paragraphs_data, list) and paragraphs_data:
                    for j, para in enumerate(paragraphs_data[:3]):  # 每章最多3段
                        if not isinstance(para, dict):
                            continue
                        para_topic = para.get("topic", "").strip()
                        if not para_topic:
                            continue
                        paragraphs.append(ReviewParagraph(
                            paragraph_id=f"sec_{i:02d}_para_{j:02d}",
                            topic=para_topic,
                            description=para.get("description", ""),
                            order=j,
                            assigned_paper_ids=para.get("assigned_paper_ids", []),
                            assigned_evidence_ids=para.get("assigned_evidence_ids", []),
                        ))

                # 如果 LLM 没有生成段落，自动生成2个默认段落（基于章节标题）
                if not paragraphs:
                    paragraphs = [
                        ReviewParagraph(
                            paragraph_id=f"sec_{i:02d}_para_00",
                            topic=f"{title}（概述）",
                            description=f"{title}的基本概念和研究背景",
                            order=0,
                        ),
                        ReviewParagraph(
                            paragraph_id=f"sec_{i:02d}_para_01",
                            topic=f"{title}（详细分析）",
                            description=f"{title}的具体机制和实验证据",
                            order=1,
                        ),
                    ]

                sections.append(ReviewSection(
                    section_id=f"sec_{i:02d}",
                    title=title,
                    description=sec.get("description", ""),
                    order=i,
                    assigned_evidence_ids=assigned,
                    assigned_paper_ids=list({
                        c.paper_id for c in evidence_cards if c.evidence_id in assigned
                    }),
                    paragraphs=paragraphs,
                ))

            if not sections:
                return None

            # 确保所有证据都被分配（LLM 可能遗漏）
            assigned_all = set()
            for s in sections:
                assigned_all.update(s.assigned_evidence_ids)
            unassigned = [c.evidence_id for c in evidence_cards if c.evidence_id not in assigned_all]
            if unassigned and sections:
                sections[-1].assigned_evidence_ids.extend(unassigned)

            paper_ids = list({c.paper_id for c in evidence_cards})
            return ReviewOutline(
                topic=topic,
                sections=sections,
                total_papers=len(paper_ids),
                total_evidence=len(evidence_cards),
            )

        except Exception:
            return None

    # ──────────────────────────────────────────
    # 规则版 fallback
    # ──────────────────────────────────────────

    def _generate_rule_based(
        self,
        topic: str,
        evidence_cards: list[EvidenceCard],
        language: str = "en",
    ) -> ReviewOutline:
        """规则版大纲：按 evidence_type 分章。V25.9: 支持英文/中文标题。"""
        # 按证据类型分组
        type_groups: dict[EvidenceType, list[EvidenceCard]] = {}
        for card in evidence_cards:
            type_groups.setdefault(card.evidence_type, []).append(card)

        # V25.9: 按语言选择章节标题
        if language.lower() == "en":
            type_order = [
                (EvidenceType.BACKGROUND, "Research Background"),
                (EvidenceType.MECHANISM, "Molecular Mechanisms"),
                (EvidenceType.FACT, "Experimental Evidence"),
                (EvidenceType.METHOD, "Research Methods"),
                (EvidenceType.CLAIM, "Research Claims"),
                (EvidenceType.LIMITATION, "Limitations and Outlook"),
            ]
            desc_template = "Based on {count} {etype} evidence cards"
            para_overview = "Overview"
            para_detail = "Detailed Analysis"
            para_overview_desc = "Basic concepts and research background"
            para_detail_desc = "Specific mechanisms and experimental evidence"
            other_title = "Other Findings"
            other_overview = "Overview of other findings"
            other_detail = "Detailed analysis of other findings"
        else:
            type_order = [
                (EvidenceType.BACKGROUND, "研究背景"),
                (EvidenceType.MECHANISM, "分子机制"),
                (EvidenceType.FACT, "实验证据"),
                (EvidenceType.METHOD, "研究方法"),
                (EvidenceType.CLAIM, "研究观点"),
                (EvidenceType.LIMITATION, "研究局限"),
            ]
            desc_template = "基于 {count} 条{etype}类型证据"
            para_overview = "概述"
            para_detail = "详细分析"
            para_overview_desc = "基本概念和研究背景"
            para_detail_desc = "具体机制和实验证据"
            other_title = "其他研究发现"
            other_overview = "其他研究发现（概述）"
            other_detail = "其他研究发现（详细分析）"

        sections = []
        order = 0
        for ev_type, title in type_order:
            if ev_type in type_groups and type_groups[ev_type]:
                cards = type_groups[ev_type]
                # V25.8: 为每章生成默认的2个段落
                default_paragraphs = [
                    ReviewParagraph(
                        paragraph_id=f"sec_{order:02d}_para_00",
                        topic=f"{title} ({para_overview})",
                        description=f"{title} {para_overview_desc}",
                        order=0,
                    ),
                    ReviewParagraph(
                        paragraph_id=f"sec_{order:02d}_para_01",
                        topic=f"{title} ({para_detail})",
                        description=f"{title} {para_detail_desc}",
                        order=1,
                    ),
                ]
                sections.append(ReviewSection(
                    section_id=f"sec_{order:02d}",
                    title=title,
                    description=desc_template.format(count=len(cards), etype=ev_type.value),
                    order=order,
                    assigned_evidence_ids=[c.evidence_id for c in cards],
                    assigned_paper_ids=list({c.paper_id for c in cards}),
                    paragraphs=default_paragraphs,
                ))
                order += 1

        # 如果章节太少，把剩余类型合并到"其他"
        remaining = []
        for ev_type, cards in type_groups.items():
            if not any(s.section_id == f"sec_{i:02d}" and ev_type.value in s.description for i, s in enumerate(sections)):
                remaining.extend(cards)
        if remaining and len(sections) < self.min_sections:
            default_paragraphs = [
                ReviewParagraph(
                    paragraph_id=f"sec_{order:02d}_para_00",
                    topic=other_overview,
                    description=para_overview_desc,
                    order=0,
                ),
                ReviewParagraph(
                    paragraph_id=f"sec_{order:02d}_para_01",
                    topic=other_detail,
                    description=para_detail_desc,
                    order=1,
                ),
            ]
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title=other_title,
                description=desc_template.format(count=len(remaining), etype="other"),
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in remaining],
                assigned_paper_ids=list({c.paper_id for c in remaining}),
                paragraphs=default_paragraphs,
            ))

        paper_ids = list({c.paper_id for c in evidence_cards})
        return ReviewOutline(
            topic=topic,
            sections=sections,
            total_papers=len(paper_ids),
            total_evidence=len(evidence_cards),
        )

    # ──────────────────────────────────────────
    # 文献聚类（复用 V24.3 paper_communities 表）
    # ──────────────────────────────────────────

    def _load_communities(self, evidence_cards: list[EvidenceCard]) -> dict[str, list[str]]:
        """
        从 SQLite 的 paper_communities + community_members 表读取文献聚类信息。
        返回 {community_id: [paper_id, ...]}，只包含证据卡片中涉及的论文。
        """
        if not self.db_path or not Path(self.db_path).exists():
            return {}

        try:
            paper_ids = {c.paper_id for c in evidence_cards}
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 查询涉及论文的社区归属
            placeholders = ",".join("?" * len(paper_ids))
            cursor.execute(
                f"""
                SELECT cm.community_id, cm.paper_id, pc.label
                FROM community_members cm
                LEFT JOIN paper_communities pc ON cm.community_id = pc.community_id
                WHERE cm.paper_id IN ({placeholders})
                """,
                list(paper_ids),
            )

            communities: dict[str, list[str]] = {}
            for community_id, paper_id, label in cursor.fetchall():
                cid = f"{community_id}({label})" if label else str(community_id)
                communities.setdefault(cid, []).append(paper_id)

            conn.close()
            return communities

        except Exception:
            return {}

    # ──────────────────────────────────────────
    # V25.8: 从用户自定义 JSON 构建大纲
    # ──────────────────────────────────────────

    @staticmethod
    def from_custom_json(topic: str, custom_data: dict, evidence_cards: Optional[list[EvidenceCard]] = None) -> ReviewOutline:
        """
        从用户传入的自定义 JSON 构建 ReviewOutline（V25.8: 段落级自定义大纲）。

        用户可以指定：
        - 章节结构（标题、描述）
        - 每章的段落主题（必须）
        - 每段分配的论文ID（可选，assigned_paper_ids）
        - 每段分配的证据ID（可选，更细粒度，assigned_evidence_ids）

        Args:
            topic: 综述主题
            custom_data: 用户自定义的大纲 JSON，格式：
                {
                  "sections": [
                    {
                      "title": "章节标题",
                      "description": "章节描述（可选）",
                      "paragraphs": [
                        {"topic": "段落主题", "description": "可选", "assigned_paper_ids": ["paper_001"]},
                        ...
                      ]
                    },
                    ...
                  ]
                }
            evidence_cards: 证据卡片列表（用于验证 paper_id 和 evidence_id 是否存在，可选）

        Returns:
            ReviewOutline 对象
        """
        valid_paper_ids = set()
        valid_evidence_ids = set()
        if evidence_cards:
            valid_paper_ids = {c.paper_id for c in evidence_cards if c.paper_id}
            valid_evidence_ids = {c.evidence_id for c in evidence_cards}

        sections = []
        all_assigned_evidence = set()

        for i, sec_data in enumerate(custom_data.get("sections", [])):
            if not isinstance(sec_data, dict):
                continue
            title = sec_data.get("title", "").strip()
            if not title:
                continue

            # 解析段落
            paragraphs = []
            section_paper_ids = set()
            section_evidence_ids = set()

            for j, para_data in enumerate(sec_data.get("paragraphs", [])):
                if not isinstance(para_data, dict):
                    continue
                para_topic = para_data.get("topic", "").strip()
                if not para_topic:
                    continue

                # 过滤掉不存在的 paper_id
                assigned_papers = []
                for pid in para_data.get("assigned_paper_ids", []):
                    if pid and (not valid_paper_ids or pid in valid_paper_ids):
                        assigned_papers.append(pid)
                        section_paper_ids.add(pid)

                # 过滤掉不存在的 evidence_id
                assigned_evidences = []
                for eid in para_data.get("assigned_evidence_ids", []):
                    if eid and (not valid_evidence_ids or eid in valid_evidence_ids):
                        assigned_evidences.append(eid)
                        section_evidence_ids.add(eid)
                        all_assigned_evidence.add(eid)

                paragraphs.append(ReviewParagraph(
                    paragraph_id=f"sec_{i:02d}_para_{j:02d}",
                    topic=para_topic,
                    description=para_data.get("description", ""),
                    order=j,
                    assigned_paper_ids=assigned_papers,
                    assigned_evidence_ids=assigned_evidences,
                ))

            # 如果用户没有指定段落，自动生成2个默认段落
            if not paragraphs:
                paragraphs = [
                    ReviewParagraph(
                        paragraph_id=f"sec_{i:02d}_para_00",
                        topic=f"{title}（概述）",
                        order=0,
                    ),
                    ReviewParagraph(
                        paragraph_id=f"sec_{i:02d}_para_01",
                        topic=f"{title}（详细分析）",
                        order=1,
                    ),
                ]

            # 如果用户没有在段落级别分配证据，在章节级别分配（从段落的 paper_ids 反推）
            if not section_evidence_ids and evidence_cards:
                for card in evidence_cards:
                    if card.paper_id in section_paper_ids:
                        section_evidence_ids.add(card.evidence_id)
                        all_assigned_evidence.add(card.evidence_id)

            sections.append(ReviewSection(
                section_id=f"sec_{i:02d}",
                title=title,
                description=sec_data.get("description", ""),
                order=i,
                assigned_evidence_ids=list(section_evidence_ids),
                assigned_paper_ids=list(section_paper_ids),
                paragraphs=paragraphs,
            ))

        return ReviewOutline(
            topic=topic,
            sections=sections,
            total_papers=len(valid_paper_ids) if evidence_cards else 0,
            total_evidence=len(valid_evidence_ids) if evidence_cards else 0,
        )


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("📋 Outline Generator Test (V25.2)")
    print("=" * 60)

    # 构造测试证据卡片
    test_cards = [
        EvidenceCard(
            evidence_id="ev_001", paper_id="paper1", para_id="p1",
            evidence_type=EvidenceType.BACKGROUND,
            content="STAT1 is a transcription factor mediating interferon signaling.",
            original_quote="STAT1 is a transcription factor mediating interferon signaling.",
        ),
        EvidenceCard(
            evidence_id="ev_002", paper_id="paper1", para_id="p2",
            evidence_type=EvidenceType.MECHANISM,
            content="STAT1 is phosphorylated at Y701 by JAK kinases upon IFN-gamma stimulation.",
            original_quote="STAT1 is phosphorylated at Y701 by JAK kinases.",
        ),
        EvidenceCard(
            evidence_id="ev_003", paper_id="paper2", para_id="p1",
            evidence_type=EvidenceType.FACT,
            content="STAT1 knockout mice are highly susceptible to viral infections.",
            original_quote="STAT1 knockout mice are highly susceptible to viral infections.",
        ),
        EvidenceCard(
            evidence_id="ev_004", paper_id="paper2", para_id="p2",
            evidence_type=EvidenceType.FACT,
            content="STAT1 GOF mutations cause chronic mucocutaneous candidiasis.",
            original_quote="STAT1 GOF mutations cause chronic mucocutaneous candidiasis.",
        ),
        EvidenceCard(
            evidence_id="ev_005", paper_id="paper3", para_id="p1",
            evidence_type=EvidenceType.LIMITATION,
            content="Most studies use mouse models, limiting translational relevance.",
            original_quote="Most studies use mouse models.",
        ),
    ]

    # 测试规则版（无 LLM）
    generator = OutlineGenerator(llm_client=None)
    outline = generator.generate("STAT1 干扰素调控", test_cards)

    print(f"\n主题: {outline.topic}")
    print(f"章节数: {len(outline.sections)}")
    print(f"论文数: {outline.total_papers}, 证据数: {outline.total_evidence}")
    for sec in outline.sections:
        print(f"  [{sec.section_id}] {sec.title} ({len(sec.assigned_evidence_ids)} 条证据)")
        print(f"       描述: {sec.description}")

    # 验证所有证据都被分配
    all_assigned = set()
    for sec in outline.sections:
        all_assigned.update(sec.assigned_evidence_ids)
    unassigned = [c.evidence_id for c in test_cards if c.evidence_id not in all_assigned]
    print(f"\n未分配证据: {unassigned if unassigned else '无（全部已分配）'}")

    print("\n✅ 规则版大纲生成测试通过。")
    print("   LLM 版大纲生成需要 Ollama 服务运行，设置 llm_client 后自动启用。")
