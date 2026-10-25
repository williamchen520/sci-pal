"""Prompt construction for one review section (pure, no LLM, no I/O).

``review_generator._write_section`` currently interleaves ~120 lines of prompt
assembly with the actual LLM call. This module is the extracted, testable half:
give it a section and its evidence cards, get back the user prompt.

The system prompt is still owned by ``review_generator`` (``WRITE_SYSTEM_PROMPT_EN``
/ ``_ZH``); callers pass it to the model themselves, so this module has no
dependency on the heavy review stack.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

#: Section-title keywords -> canonical section type.
SECTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("introduction", ("introduction", "background", "前言", "引言", "背景")),
    ("methods", ("method", "methodology", "approach", "方法", "材料")),
    ("results", ("result", "finding", "结果", "发现")),
    ("discussion", ("discussion", "讨论")),
    ("conclusion", ("conclusion", "summary", "perspective", "future", "结论", "总结", "展望")),
)

SECTION_HINTS = {
    "en": {
        "introduction": "This is the INTRODUCTION section. Start with broad context, narrow down to the specific topic, state the review's scope and objectives, and end with a brief roadmap of the review.",
        "methods": "This is the METHODS section. Be precise and structured, describe search strategies, inclusion/exclusion criteria, data extraction, and analysis methods clearly. Use a systematic, objective tone.",
        "results": "This is the RESULTS section. Present findings objectively, organize by themes or subtopics, report quantitative data where available, and avoid interpretation (save that for Discussion).",
        "discussion": "This is the DISCUSSION section. Interpret the findings, compare across studies, explain contradictions, discuss mechanisms and implications, acknowledge limitations, and suggest future directions.",
        "conclusion": "This is the CONCLUSION section. Summarize the key findings concisely, emphasize the main contributions, discuss broader implications, and end with a forward-looking perspective. Do not introduce new evidence.",
        "body": "This is a main body section. Present and synthesize the evidence, organize by logical themes, compare and contrast findings, and build toward the overall narrative.",
    },
    "zh": {
        "introduction": "这是引言部分。从宏观背景切入，逐步聚焦到具体主题，明确综述的范围和目标，最后简要介绍综述的结构安排。",
        "methods": "这是方法学部分。要精确、有条理，清晰描述检索策略、纳入排除标准、数据提取和分析方法。使用系统、客观的语气。",
        "results": "这是结果部分。客观呈现研究发现，按主题或子主题组织，有定量数据时要报告，避免过度解读（解读放在讨论部分）。",
        "discussion": "这是讨论部分。解读研究发现，跨研究比较，解释矛盾，讨论机制和意义，承认局限性，提出未来方向。",
        "conclusion": "这是结论部分。简明总结主要发现，强调核心贡献，讨论更广泛的意义，以前瞻性视角结尾。不要引入新的证据。",
        "body": "这是正文主体部分。呈现和综合证据，按逻辑主题组织，比较和对比不同研究的发现，构建整体叙事。",
    },
}

REVIEW_TYPE_HINTS = {
    "en": {
        "narrative": "Organize by logical threads, progressing layer by layer, telling the research story clearly.",
        "comparative": "Focus on comparing differences between experimental methods, model systems, and conditions.",
        "systematic": "Maintain methodological rigor, explicitly describe evidence sources and quality.",
    },
    "zh": {
        "narrative": "按逻辑线索组织，层层递进，像讲故事一样把研究脉络讲清楚。",
        "comparative": "重点对比不同实验方法、模型系统和实验条件之间的差异，明确指出哪些研究用了什么方法、得出了什么不同结论。",
        "systematic": "保持方法学严谨性，明确描述证据来源和质量，区分事实和推断，强调证据的一致性和差异性。",
    },
}

REVIEW_TYPE_LABELS = {
    "en": {
        "narrative": "Narrative Review",
        "comparative": "Comparative Review",
        "systematic": "Systematic Review",
    },
    "zh": {
        "narrative": "叙事型综述",
        "comparative": "实验对比型综述",
        "systematic": "系统综述型",
    },
}


def detect_section_type(title: str) -> str:
    """Map a section title to introduction/methods/results/discussion/conclusion/body."""
    lowered = str(title or "").lower()
    for section_type, keywords in SECTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return section_type
    return "body"


def evidence_lines(evidence: Sequence[Mapping[str, Any]]) -> str:
    """Render evidence cards as the ``[id] (type) content`` block."""
    lines: list[str] = []
    for card in evidence:
        evidence_id = card.get("evidence_id", "")
        evidence_type = card.get("evidence_type", "fact")
        if hasattr(evidence_type, "value"):
            evidence_type = evidence_type.value
        lines.append(f"[{evidence_id}] ({evidence_type}) {card.get('content', '')}\n")
        quote = str(card.get("original_quote") or "")
        if quote:
            lines.append(f"  Quote: {quote[:200]}\n")
    return "".join(lines)


def build_write_prompt(
    section: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    *,
    review_type: str = "narrative",
    language: str = "en",
    previous_summary: str = "",
    feedback: str = "",
    section_index: int = 0,
    total_sections: int = 1,
) -> tuple[str, str]:
    """Return ``(section_type, user_prompt)`` for one section draft."""
    lang = "zh" if str(language).lower().startswith("zh") else "en"
    section_type = detect_section_type(str(section.get("title", "")))
    review_key = str(review_type).lower()

    hint = SECTION_HINTS[lang].get(section_type, SECTION_HINTS[lang]["body"])
    type_hint = REVIEW_TYPE_HINTS[lang].get(review_key, REVIEW_TYPE_HINTS[lang]["narrative"])
    type_label = REVIEW_TYPE_LABELS[lang].get(review_key, REVIEW_TYPE_LABELS[lang]["narrative"])

    title = str(section.get("title", ""))
    description = str(section.get("description", ""))
    evidence_text = evidence_lines(evidence)

    if lang == "en":
        context_block = ""
        if previous_summary:
            context_block = (
                "Previous sections summary (for coherence, do NOT repeat this content):\n"
                f"{previous_summary}\n\n"
            )
        feedback_block = ""
        if feedback:
            feedback_block = (
                "## Previous Draft Review Feedback (you are REVISING the draft based on this feedback):\n"
                f"{feedback}\n\n"
                "Please address ALL the issues and suggestions above in your revised draft.\n\n"
            )
        prompt = (
            f"Review type: {type_label}\n"
            f"Writing style: {type_hint}\n"
            f"Section type: {section_type}\n"
            f"Section-specific guidance: {hint}\n\n"
            f"Section position: Section {section_index + 1} of {total_sections}\n\n"
            f"Section title: {title}\n"
            f"Section description: {description}\n\n"
            f"{context_block}"
            f"{feedback_block}"
            f"Available evidence cards:\n{evidence_text}\n\n"
            "## Writing Process (Claims-Evidence Matrix):\n"
            "Step 1: Identify 3-5 key claims (main points) this section should make.\n"
            "Step 2: For each claim, explicitly map which evidence card IDs support it (e.g., Claim 1 ← [ev_001, ev_003]).\n"
            "Step 3: Write the section text based ONLY on these evidence-backed claims. "
            "Every declarative sentence must trace back to at least one evidence card.\n\n"
            "Based on the above evidence cards, write the review text for this section (200-400 words). "
            "Every declarative sentence must end with a [evidence_id] citation marker. "
            "Do NOT repeat content already covered in previous sections. "
            "Do NOT make claims that are not supported by the provided evidence cards."
        )
        return section_type, prompt

    context_block = ""
    if previous_summary:
        context_block = f"前文摘要（用于保持连贯，不要重复这些内容）：\n{previous_summary}\n\n"
    feedback_block = ""
    if feedback:
        feedback_block = (
            "## 初稿评审反馈（你正在根据此反馈修订初稿）：\n"
            f"{feedback}\n\n"
            "请在修订稿中解决上述所有问题和建议。\n\n"
        )
    prompt = (
        f"综述模板类型：{type_label}\n"
        f"写作风格要求：{type_hint}\n"
        f"章节类型：{section_type}\n"
        f"章节写作指导：{hint}\n\n"
        f"章节位置：第 {section_index + 1} / {total_sections} 章\n\n"
        f"章节标题：{title}\n"
        f"章节描述：{description}\n\n"
        f"{context_block}"
        f"{feedback_block}"
        f"可用证据卡片：\n{evidence_text}\n\n"
        "## 写作流程（证据-声明矩阵）：\n"
        "第一步：先确定本章要讲的 3-5 个核心要点（声明）。\n"
        "第二步：为每个要点明确映射支持它的证据卡片ID（例如：要点1 ← [ev_001, ev_003]）。\n"
        "第三步：仅基于这些有证据支撑的要点来撰写正文。每个陈述句都必须能追溯到至少一个证据卡片。\n\n"
        "请根据以上证据卡片，撰写本章节的综述正文（200-400字）。"
        "每个陈述句末尾必须标注 [证据ID] 引用标记。"
        "不要重复前面章节已经讲过的内容。"
        "不要做出没有证据卡片支撑的声明。"
    )
    return section_type, prompt


def count_citation_markers(text: str) -> int:
    """Count ``[ev_...]`` markers (used by callers to sanity-check output)."""
    return len(re.findall(r"\[ev_[^\]]+\]", str(text or "")))
