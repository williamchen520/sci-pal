"""
V25.0 - 综述生成主流程（ReviewGenerator）。

串联完整流水线：
  用户主题 → 检索 → 证据抽取 → 大纲生成 → 撰写 → 引用校验 → Markdown 输出

V25.0 范围：
- 检索：复用 UnifiedRetriever
- 证据抽取：EvidenceExtractor（LLM）
- 大纲：简单规则生成（按证据类型/章节分组），或接受用户传入大纲
- 撰写：LLM 基于证据卡片写段落，严格限制只能用证据内容
- 校验：CitationVerifier（确定性 + 可选 LLM 深度校验）
- 输出：Markdown（仅含已验证句子 + 参考文献列表）

用法:
    generator = ReviewGenerator(llm_client, retriever)
    output = generator.generate(topic="STAT1 干扰素调控", max_papers=20)
    print(output.markdown)
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .citation_formatter import PaperMetadata, build_metadata_from_db_row, format_citation, format_citation_list, get_missing_fields_report, get_supported_styles, metadata_to_csl_json
from .citation_verifier import CitationVerifier
from .evidence_extractor import EvidenceExtractor
from .llm_client import LLMClient, LLMError
from .models import (
    EvidenceCard,
    EvidenceType,
    ReviewDraft,
    ReviewOutput,
    ReviewOutline,
    ReviewParagraph,
    ReviewSection,
    ReviewSentence,
    SentenceStatus,
)


# ──────────────────────────────────────────────
# 撰写 Agent Prompt（V25.9: 英文默认，保留中文向后兼容）
# ──────────────────────────────────────────────

WRITE_SYSTEM_PROMPT_EN = """You are an academic review writer. Your task is to write a section of a review based on the provided evidence cards.

【IRON RULE — Every sentence must have a citation, violations will be rejected by the system】
1. Only use content explicitly stated in the evidence cards. Never fabricate any data, mechanism, or conclusion.
2. **Every complete sentence must end with a citation marker** in the format [evidence_id]. This includes:
   - Declarative sentences, summary sentences, transition sentences, inference sentences — ALL must be marked
   - **Summary sentences at the end of a paragraph must also have citations** — no uncited "In summary", "Thus", "This suggests" allowed
   - If a sentence cannot be tied to any evidence card, **do not write it at all** — better to write one fewer sentence than an uncited one
   - Transition sentences without specific evidence support should be deleted; connect directly with evidence-backed sentences
3. If a claim is supported by multiple evidence cards, mark all relevant IDs, e.g., [ev_1][ev_2]
4. Do not write vague phrases like "Studies have shown", "It is well known", "A large body of research confirms" without specific evidence
5. Distinguish facts from claims: experimental data in declarative tone; author opinions as "XX et al. argue that"
6. If evidence cards contradict each other, explicitly note "there is controversy" and list different viewpoints separately
7. Do not add references not present in the evidence cards

【Academic Writing Style Rules — Cell/Nature/Science top journal standard】
8. **TENSE RULES (CRITICAL)**
   - Use present tense for established facts, natural laws, and universally accepted knowledge.
     Example: "STAT1 is a key mediator of interferon signaling."
   - Use past tense for experimental methods, results, and findings from specific studies.
     Example: "We found that STAT1 phosphorylation increased by 3-fold [ev_001]."
   - Use present tense for conclusions, interpretations, and implications.
     Example: "These findings suggest that STAT1 plays a crucial role in..."

9. **VOICE RULES**
   - Prefer active voice over passive voice whenever possible.
     Better: "We measured the expression levels."
     Worse: "The expression levels were measured."
   - Use passive voice only when the actor is unimportant or unknown.
     Example: "Samples were collected from patients [ev_002]."

10. **STYLE RULES**
    - Write clearly and concisely. Avoid wordiness.
      Better: "STAT1 regulates IFN signaling."
      Worse: "It is known that STAT1 plays an important role in the regulation of interferon signaling."
    - Avoid hyperbolic language. Do not use words like "novel," "unprecedented," or "remarkable."
    - Use formal scientific language. Avoid colloquialisms.
    - Average sentence length: 15-20 words. Keep sentences clear and focused.
    - Use transitions to connect ideas: "However," "In contrast," "Consistent with previous reports."

11. **DO NOT**
    - Do not use contractions (e.g., "don't" → "do not")
    - Do not make claims without evidence
    - Do not overstate findings
    - Do not use vague language (e.g., "very," "quite," "somewhat")

12. **Write in English**

【Plan before writing — mandatory】
Before writing, mentally complete the following planning (do not output the planning process, output the text directly):
1. List all available evidence card IDs for this section
2. Pre-assign evidence IDs to each sentence
3. If you have an idea but cannot find corresponding evidence, abandon that idea — do not write it
4. Ensure every sentence has at least one evidence ID bound

【Wrong examples — never write like this】
❌ "This suggests that STAT1 plays a key role in immune responses." (no citation marker, will be rejected)
❌ "In summary, STAT1 deficiency leads to multiple diseases." (summary sentence without citation, will be rejected)
❌ "Furthermore, STAT1 is also involved in other signaling pathways." (transition sentence without specific evidence, will be rejected)
❌ "Studies have shown that STAT1 phosphorylation is a key step in its activation." ("Studies have shown" is vague, no specific evidence ID)
❌ "STAT1 plays a very important role in immune responses." (vague language "very important")
❌ "It is known that STAT1 is a key mediator of interferon signaling." (wordy, "It is known that")

【Correct examples】
✅ "STAT1 is phosphorylated at Y701 upon IFN-gamma stimulation [ev_001]."
✅ "STAT1 knockout mice are highly susceptible to viral infections [ev_002][ev_003]."
✅ "In patients with partial STAT1 deficiency, STAT1 protein expression levels are reduced [ev_004]."
✅ "Consistent with previous reports, STAT1 deficiency leads to impaired antiviral responses [ev_005]."

Output format: directly output the section's Markdown text. Do not output the section title (the system adds it). Do not include any explanations."""

# 中文撰写 prompt（保留向后兼容，language=zh 时使用）
WRITE_SYSTEM_PROMPT_ZH = """你是一个科研综述撰写器。你的任务是根据提供的证据卡片，撰写综述的一个章节。

【铁律 — 每一句都必须有引用，违反即被系统拒绝】
1. 只能使用证据卡片中明确陈述的内容，绝对不能编造任何数据、机制或结论
2. **每一个完整句子末尾必须标注引用标记**，格式为 [证据ID]。这包括：
   - 陈述句、总结句、过渡句、推断句 —— 全部都要标
   - **段落末尾的总结句也必须有引用**，不允许出现没有引用的"综上所述""由此可见""这表明"
   - 如果某句话无法绑定到任何证据卡片，**直接不写这句话**，宁可少写一句也不要写无引用的句子
   - 过渡句如果没有具体证据支撑，就删掉，用有证据的句子直接衔接
3. 如果某个观点有多条证据支撑，标注所有相关ID，如 [ev_1][ev_2]
4. 不要写"研究表明""众所周知""大量研究证实"等没有具体证据的套话
5. 区分事实和论断：实验数据用陈述语气，作者观点用"XX等人认为"
6. 如果证据卡片之间存在矛盾，明确指出"存在争议"并分别列出不同观点
7. 不要添加证据卡片中没有的参考文献

【学术写作规范 — Cell/Nature/Science 顶刊标准】
8. **时态规则（关键）**
   - 已确立的事实、自然规律和普遍接受的知识用现在时。
     例："STAT1是干扰素信号传导的关键介质。"
   - 具体研究的实验方法、结果和发现用过去时。
     例："我们发现STAT1磷酸化水平增加了3倍 [ev_001]。"
   - 结论、解释和意义用现在时。
     例："这些发现表明STAT1在...中发挥关键作用。"

9. **语态规则**
   - 尽可能用主动语态，少用被动语态。
     更好："我们测量了表达水平。"
     更差："表达水平被测量了。"
   - 只有当施动者不重要或未知时才用被动语态。
     例："样本来自患者 [ev_002]。"

10. **风格规则**
    - 写作清晰简洁，避免冗长。
      更好："STAT1调控干扰素信号。"
      更差："众所周知，STAT1在干扰素信号调控中发挥重要作用。"
    - 避免夸张的语言。不要用"新颖的""前所未有的""显著的"等词。
    - 使用正式的科学语言，避免口语化。
    - 平均句子长度：15-20 字。保持句子清晰聚焦。
    - 使用过渡词连接观点："然而""相比之下""与既往报告一致"。

11. **不要做的事**
    - 不要使用缩写（如"don't"→"do not"）
    - 不要提出没有证据的主张
    - 不要夸大发现
    - 不要使用模糊语言（如"非常""相当""有点"）

12. **用中文写作**

【写作前先规划 — 强制执行】
在开始写之前，先在心里完成以下规划（不要输出规划过程，直接输出正文）：
1. 列出本章所有可用的证据卡片ID
2. 为每一句话预先分配要绑定的证据ID
3. 如果有想法但找不到对应证据，直接放弃这个想法，不要写
4. 确保每一句话都有至少一个证据ID绑定

【错误示例 — 绝对不要这样写】
❌ "这表明STAT1在免疫反应中扮演关键角色。"（没有引用标记，会被拒绝）
❌ "综上所述，STAT1缺陷导致多种疾病。"（总结句没有引用，会被拒绝）
❌ "此外，STAT1还参与其他信号通路。"（过渡句没有具体证据，会被拒绝）
❌ "研究表明，STAT1磷酸化是其激活的关键步骤。"（"研究表明"是套话，没有具体证据ID）
❌ "STAT1在免疫反应中发挥非常重要的作用。"（模糊语言"非常重要"）
❌ "众所周知，STAT1是干扰素信号传导的关键介质。"（冗长，"众所周知"）

【正确示例】
✅ "STAT1在IFN-gamma刺激下被磷酸化于Y701位点 [ev_001]。"
✅ "STAT1敲除小鼠对病毒感染高度易感 [ev_002][ev_003]。"
✅ "在AR部分STAT1缺陷患者中，STAT1蛋白表达水平降低 [ev_004]。"
✅ "与既往报告一致，STAT1缺陷导致抗病毒反应受损 [ev_005]。"

输出格式：直接输出章节的 Markdown 文本，不要输出章节标题（标题由系统添加），不要任何解释。"""

# 默认使用英文
WRITE_SYSTEM_PROMPT = WRITE_SYSTEM_PROMPT_EN


# ──────────────────────────────────────────────
# 综述生成器
# ──────────────────────────────────────────────

class ReviewGenerator:
    """
    综述生成主流程控制器。

    Args:
        llm_client: LLMClient 实例
        retriever: UnifiedRetriever 实例（用于检索相关文献）
        max_evidence_per_paper: 每篇论文最多保留的证据数，默认 5
        use_llm_verification: 是否启用 LLM 深度校验，默认 False（V25.0 先用确定性校验）
    """

    def __init__(
        self,
        llm_client: LLMClient,
        retriever=None,
        max_evidence_per_paper: int = 5,
        use_llm_verification: bool = False,
        db_path: Optional[str] = None,
    ):
        self.llm = llm_client
        self.retriever = retriever
        self.max_evidence_per_paper = max_evidence_per_paper
        self.use_llm_verification = use_llm_verification
        self.db_path = db_path  # V25.7: 保存数据库路径，用于查询论文元数据做参考文献格式化
        # V25.4 优化：轻量任务（证据抽取/关系抽取/冲突识别）用轻量模型
        # （从环境变量 SCIPAL_LLM_LIGHT_MODEL 读取，本地默认 qwen2.5:7b，云端默认 qwen-turbo）
        # 只有大纲生成和撰写保留重模型（需要更强的语言组织能力）
        from .llm_client import create_llm_client
        self._light_llm = create_llm_client(light=True, timeout=300, max_retries=2)
        self.extractor = EvidenceExtractor(self._light_llm)
        self.verifier = CitationVerifier(llm_client if use_llm_verification else None)
        # V25.2: LLM 大纲生成器（复用文献聚类信息需要 db_path）—— 用14b
        from .outline_generator import OutlineGenerator
        self.outline_generator = OutlineGenerator(llm_client, db_path=db_path)
        # V25.3: 关系抽取器 + 冲突识别 Agent —— 用7b
        from .relation_extractor import RelationExtractor
        from .conflict_detector import ConflictDetector
        self.relation_extractor = RelationExtractor(self._light_llm)
        self.conflict_detector = ConflictDetector(self._light_llm)
        # V25.6: 保存最后一次生成的 draft 和 evidence_cards，用于前端点击溯源
        self._last_draft: Optional[ReviewDraft] = None
        self._last_evidence_cards: list[EvidenceCard] = []
        # V25.7: 自动补引用计数器（每次 generate 开始时清零）
        self._auto_cite_count: int = 0

    def generate(
        self,
        topic: str,
        max_papers: int = 20,
        outline: Optional[ReviewOutline] = None,
        citation_style: str = "apa",
        review_type: str = "narrative",
        custom_outline: Optional[dict] = None,
        language: str = "en",
        include_abstracts: bool = True,
        selected_paper_ids: Optional[list[str]] = None,
        excluded_paper_ids: Optional[list[str]] = None,
    ) -> ReviewOutput:
        """
        生成综述。

        Args:
            topic: 综述主题
            max_papers: 最多检索的论文数
            outline: 可选用户自定义大纲（ReviewOutline 对象）；不传则自动生成
            citation_style: 参考文献格式（apa / nature / vancouver），默认 apa
            review_type: 综述模板类型（V25.7）：
                - "narrative": 叙事型（默认，按逻辑线索组织）
                - "comparative": 实验对比型（按方法/模型对比）
                - "systematic": 系统综述型（严格方法学结构）
            custom_outline: V25.8 用户自定义段落级大纲（JSON 格式），优先级高于 outline 和自动生成。
                格式：{"sections": [{"title": "...", "paragraphs": [{"topic": "...", "assigned_paper_ids": [...]}]}]}
            language: V25.9: 综述生成语言，"en"（默认，英文）或 "zh"（中文）
            include_abstracts: V26.0: 是否包含摘要库的论文，默认 True
            selected_paper_ids: V26.0: 用户选定的论文 ID 列表，如果指定则只用这些论文
            excluded_paper_ids: V26.0: 用户要剔除的论文 ID 列表

        Returns:
            ReviewOutput（含 Markdown 全文、参考文献、统计、警告）
        """
        warnings: list[str] = []

        # ── Step 1: 检索 ──
        paragraphs = self._retrieve(
            topic,
            max_papers,
            include_abstracts=include_abstracts,
            selected_paper_ids=selected_paper_ids,
            excluded_paper_ids=excluded_paper_ids,
        )
        if not paragraphs:
            return ReviewOutput(
                topic=topic,
                markdown=f"# {topic}\n\n未检索到相关文献。",
                stats={"total_sentences": 0, "total_evidence": 0},
                warnings=["未检索到相关文献，请调整主题或增加 max_papers。"],
            )
        warnings.append(f"📚 检索到 {len(paragraphs)} 个相关段落。")

        # ── Step 2: 证据抽取 ──
        evidence_cards = self.extractor.extract_from_paragraphs(paragraphs, topic=topic, language=language)
        # 每篇论文限数
        evidence_cards = self._limit_evidence_per_paper(evidence_cards)
        if not evidence_cards:
            return ReviewOutput(
                topic=topic,
                markdown=f"# {topic}\n\n未能从文献中抽取到有效证据。",
                stats={"total_sentences": 0, "total_evidence": 0},
                warnings=["证据抽取失败或所有段落均为 boilerplate。"],
            )
        warnings.append(f"🔍 抽取到 {len(evidence_cards)} 条证据卡片。")

        # ── Step 2.5: 全局短 ID 重映射（V25.1）──
        # 将长 evidence_id 统一映射为 ev_001, ev_002... 短序号，
        # 避免 paper_id 含空格/特殊字符导致 LLM 引用标记解析失败。
        evidence_cards = self._remap_to_short_ids(evidence_cards)
        evidence_dict = {c.evidence_id: c for c in evidence_cards}

        # ── Step 3: 大纲（V25.2: LLM 大纲生成；V25.8: 支持用户自定义段落级大纲）──
        if custom_outline is not None:
            # V25.8: 用户自定义段落级大纲（优先级最高）
            from .outline_generator import OutlineGenerator
            outline = OutlineGenerator.from_custom_json(topic, custom_outline, evidence_cards=evidence_cards)
            total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)
            warnings.append(f"📝 使用用户自定义大纲：{len(outline.sections)} 个章节，{total_paragraphs} 个段落。")
        elif outline is None:
            # 自动生成大纲（LLM 优先，规则版 fallback）
            outline = self.outline_generator.generate(topic, evidence_cards, use_communities=True, review_type=review_type, language=language)
            total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)
            warnings.append(f"📋 大纲包含 {len(outline.sections)} 个章节，{total_paragraphs} 个段落。")
        else:
            total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)
            warnings.append(f"📋 使用传入大纲：{len(outline.sections)} 个章节，{total_paragraphs} 个段落。")

        # ── Step 3.5: 关系抽取 + 冲突识别（V25.3）──
        relations = self.relation_extractor.extract(evidence_cards)
        conflicts = self.conflict_detector.detect(evidence_cards, relations, language=language)
        contradictions = [r for r in relations if r.relation_type.value == "contradicts"]
        warnings.append(f"🔗 抽取到 {len(relations)} 条证据间关系（{len(contradictions)} 条矛盾）")
        if conflicts:
            true_controv = [c for c in conflicts if getattr(c, 'conflict_type', 'true_controversy') == 'true_controversy']
            cond_diff = [c for c in conflicts if getattr(c, 'conflict_type', 'true_controversy') == 'condition_difference']
            warning_parts = [f'⚔️  识别到 {len(conflicts)} 个冲突点']
            if true_controv:
                warning_parts.append(f'其中 {len(true_controv)} 个为真正争议')
            if cond_diff:
                warning_parts.append(f'{len(cond_diff)} 个为条件差异型（将单独成节呈现）')
            warnings.append('，'.join(warning_parts) + '。')

        # ── Step 4: 撰写 ──
        self._auto_cite_count = 0  # V25.7: 每次生成前清零自动补引用计数器
        draft = self._write_draft(topic, outline, evidence_dict, review_type=review_type, language=language)
        warnings.append(f"✍️  撰写完成，共 {len(draft.sentences)} 句。")
        if self._auto_cite_count > 0:
            warnings.append(f"🔧 后处理自动补引用 {self._auto_cite_count} 句（从同章节证据中关键词匹配，建议人工复核）。")

        # ── Step 5: 校验 ──
        draft, verify_warnings = self.verifier.verify(draft, use_llm=self.use_llm_verification)
        warnings.extend(verify_warnings)

        # ── Step 6: 输出 Markdown（V25.3: 含研究争议章节）──
        # V25.7: 查询论文元数据，用于多格式参考文献格式化
        paper_metadata_map = self._fetch_paper_metadata(evidence_cards)
        markdown = self._render_markdown(topic, draft, evidence_dict, conflicts=conflicts, paper_metadata_map=paper_metadata_map, citation_style=citation_style, language=language)
        references = self._build_references(evidence_cards, paper_metadata_map=paper_metadata_map, citation_style=citation_style)

        # V25.6: 保存最后一次的 draft 和 evidence_cards，用于前端点击溯源
        self._last_draft = draft
        self._last_evidence_cards = evidence_cards

        return ReviewOutput(
            topic=topic,
            markdown=markdown,
            references=references,
            stats=draft.stats(),
            warnings=warnings,
            relations=[r.model_dump() for r in relations],
            conflicts=[c.model_dump() for c in conflicts],
            review_type=review_type,
        )

    def generate_outline(
        self,
        topic: str,
        max_papers: int = 20,
        review_type: str = "narrative",
        custom_outline: Optional[dict] = None,
        language: str = "en",
        include_abstracts: bool = True,
        selected_paper_ids: Optional[list[str]] = None,
        excluded_paper_ids: Optional[list[str]] = None,
        task_id: Optional[str] = None,  # V26.3: 用于取消任务
    ) -> dict:
        """
        V25.8: 只生成段落级大纲（不撰写），供用户查看和修改。
        V25.9: 支持 language 参数（默认英文）。
        V26.0: 支持包含摘要库、用户选定或剔除论文。
        V26.3: 支持 task_id 参数，可取消任务。

        返回包含：
        - topic: 综述主题
        - outline: 段落级大纲（章节→段落→每段主题→每段分配的论文/证据）
        - evidence_cards: 证据卡片列表（供用户了解每篇论文写了什么）
        - papers: 涉及的论文列表（paper_id + title）
        - stats: 统计信息
        """
        # ── Step 1: 检索 ──
        if task_id:
            from .task_manager import task_manager
            task_manager.update_progress(task_id, "检索文献中...")
        paragraphs = self._retrieve(
            topic,
            max_papers,
            include_abstracts=include_abstracts,
            selected_paper_ids=selected_paper_ids,
            excluded_paper_ids=excluded_paper_ids,
        )

        # V26.3: 检查是否被取消
        if task_id:
            from .task_manager import task_manager
            if task_manager.is_cancelled(task_id):
                raise Exception("Task cancelled by user")

        if not paragraphs:
            return {
                "topic": topic,
                "outline": {"sections": []},
                "evidence_cards": [],
                "papers": [],
                "stats": {"total_paragraphs": 0, "total_evidence": 0, "total_papers": 0},
                "warnings": ["未检索到相关文献。"],
            }

        # ── Step 2: 证据抽取 ──
        if task_id:
            from .task_manager import task_manager
            task_manager.update_progress(task_id, "抽取证据中...")
        evidence_cards = self.extractor.extract_from_paragraphs(paragraphs, topic=topic, language=language)
        evidence_cards = self._limit_evidence_per_paper(evidence_cards)

        # V26.3: 检查是否被取消
        if task_id:
            from .task_manager import task_manager
            if task_manager.is_cancelled(task_id):
                raise Exception("Task cancelled by user")

        if not evidence_cards:
            return {
                "topic": topic,
                "outline": {"sections": []},
                "evidence_cards": [],
                "papers": [],
                "stats": {"total_paragraphs": len(paragraphs), "total_evidence": 0, "total_papers": 0},
                "warnings": ["证据抽取失败或所有段落均为 boilerplate。"],
            }

        # 短 ID 重映射
        evidence_cards = self._remap_to_short_ids(evidence_cards)
        evidence_dict = {c.evidence_id: c for c in evidence_cards}

        # ── Step 3: 生成大纲 ──
        # V26.3: 检查是否被取消
        if task_id:
            from .task_manager import task_manager
            task_manager.update_progress(task_id, "生成大纲中...")
            if task_manager.is_cancelled(task_id):
                raise Exception("Task cancelled by user")

        if custom_outline is not None:
            from .outline_generator import OutlineGenerator
            outline = OutlineGenerator.from_custom_json(topic, custom_outline, evidence_cards=evidence_cards)
        else:
            outline = self.outline_generator.generate(topic, evidence_cards, use_communities=True, review_type=review_type, language=language)

        # V26.1: 构建论文列表 - 从 paragraphs 里提取所有论文，不只是 evidence_cards 里的
        paper_map = {}
        for p in paragraphs:
            pid = p.get("paper_id", "")
            if not pid:
                continue
            if pid not in paper_map:
                paper_map[pid] = {
                    "paper_id": pid,
                    "title": p.get("paper_title", pid),
                    "source": p.get("source", "full_text"),
                    "evidence_count": 0,
                }
        # 统计每篇论文的证据数量
        for c in evidence_cards:
            if c.paper_id in paper_map:
                paper_map[c.paper_id]["evidence_count"] += 1
        papers = list(paper_map.values())
        paper_ids = list(paper_map.keys())  # V26.1: 保留 paper_ids 变量，兼容后面的代码

        # 构建可序列化的大纲（包含段落主题和分配的论文）
        outline_json = {
            "sections": []
        }
        for sec in outline.sections:
            sec_data = {
                "section_id": sec.section_id,
                "title": sec.title,
                "description": sec.description,
                "assigned_paper_ids": sec.assigned_paper_ids,
                "paragraphs": [],
            }
            for para in sec.paragraphs:
                para_data = {
                    "paragraph_id": para.paragraph_id,
                    "topic": para.topic,
                    "description": para.description,
                    "assigned_paper_ids": para.assigned_paper_ids,
                    "assigned_evidence_ids": para.assigned_evidence_ids,
                }
                sec_data["paragraphs"].append(para_data)
            outline_json["sections"].append(sec_data)

        total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)

        return {
            "topic": topic,
            "review_type": review_type,
            "outline": outline_json,
            "evidence_cards": [
                {
                    "evidence_id": c.evidence_id,
                    "paper_id": c.paper_id,
                    "content": c.content,
                    "evidence_type": c.evidence_type.value,
                    "section_l1": c.section_l1,
                }
                for c in evidence_cards
            ],
            "papers": papers,
            "stats": {
                "total_paragraphs_retrieved": len(paragraphs),
                "total_evidence": len(evidence_cards),
                "total_papers": len(paper_ids),
                "total_sections": len(outline.sections),
                "total_paragraphs": total_paragraphs,
            },
            "warnings": [
                f"检索到 {len(paragraphs)} 个段落，抽取到 {len(evidence_cards)} 条证据，涉及 {len(paper_ids)} 篇论文。",
                f"生成大纲：{len(outline.sections)} 个章节，{total_paragraphs} 个段落。",
            ],
        }

    # ──────────────────────────────────────────
    # 内部步骤
    # ──────────────────────────────────────────

    def _retrieve(
        self,
        topic: str,
        max_papers: int,
        include_abstracts: bool = True,
        selected_paper_ids: Optional[list[str]] = None,
        excluded_paper_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """调用检索层获取相关段落。

        V26.0: 支持同时检索全文库和摘要库，支持用户选定或剔除论文。
        """
        if self.retriever is None:
            return []

        try:
            result = self.retriever.retrieve(
                query=topic,
                top_paragraphs=max_papers,
                top_figures=0,
            )
            paragraphs = []
            for p in result.get("paragraphs", []):
                paper_id = p.get("paper_id", "")

                # V26.0: 如果用户指定了要剔除的论文，跳过
                if excluded_paper_ids and paper_id in excluded_paper_ids:
                    continue

                # V26.0: 如果用户指定了要选定的论文，只保留这些
                if selected_paper_ids and paper_id not in selected_paper_ids:
                    continue

                paragraphs.append({
                    "para_id": p.get("para_id", ""),
                    "paper_id": paper_id,
                    "text": p.get("text", ""),
                    "section_l1": p.get("section_l1", ""),
                    "page": p.get("page", 0),
                    "paper_title": p.get("paper_title", ""),
                    "source": p.get("source", "full_text"),  # V26.0: 标注来源
                })

            # V26.0: 如果需要包含摘要库，也检索摘要库
            if include_abstracts and hasattr(self.retriever, 'abstract_searcher'):
                try:
                    abstract_results = self.retriever.abstract_searcher.search(
                        topic, top_k=max_papers
                    )
                    for a in abstract_results:
                        # V26.0: 摘要库返回的是 pmid，不是 paper_id
                        paper_id = a.get("paper_id", "") or a.get("pmid", "")

                        # V26.0: 如果用户指定了要剔除的论文，跳过
                        if excluded_paper_ids and paper_id in excluded_paper_ids:
                            continue

                        # V26.0: 如果用户指定了要选定的论文，只保留这些
                        if selected_paper_ids and paper_id not in selected_paper_ids:
                            continue

                        paragraphs.append({
                            "para_id": f"abstract_{paper_id}",
                            "paper_id": paper_id,
                            "text": a.get("abstract", ""),
                            "section_l1": "Abstract",
                            "page": 0,
                            "paper_title": a.get("title", ""),
                            "source": "abstract",  # V26.0: 标注是摘要
                        })
                except Exception as e:
                    print(f"⚠️  摘要库检索失败: {e}")

            print(f"📚 检索到 {len(paragraphs)} 个相关段落")
            return paragraphs
        except Exception as e:
            print(f"⚠️  检索失败: {e}")
            return []

    def _limit_evidence_per_paper(self, cards: list[EvidenceCard]) -> list[EvidenceCard]:
        """每篇论文最多保留 max_evidence_per_paper 条证据（按置信度排序）。"""
        by_paper: dict[str, list[EvidenceCard]] = defaultdict(list)
        for c in cards:
            by_paper[c.paper_id].append(c)

        result = []
        for paper_id, paper_cards in by_paper.items():
            paper_cards.sort(key=lambda c: c.confidence, reverse=True)
            result.extend(paper_cards[:self.max_evidence_per_paper])
        return result

    @staticmethod
    def _remap_to_short_ids(cards: list[EvidenceCard]) -> list[EvidenceCard]:
        """V25.1: 将长 evidence_id 全局重映射为 ev_001, ev_002... 短序号。

        原因：paper_id 可能含空格/特殊字符（如文件名直接当 ID），
        导致 evidence_id 超长且 LLM 撰写时引用标记容易截断/格式错乱，
        校验阶段匹配不上而被误拒。重映射后：
        - LLM 看到的证据 ID 是短序号，写 [ev_001] 不会出错
        - paper_id / para_id 字段保留原始值，用于溯源
        - 输出参考文献时从 card 字段查，不依赖 evidence_id
        """
        for i, card in enumerate(cards):
            card.evidence_id = f"ev_{i + 1:03d}"
        return cards

    def _generate_simple_outline(
        self,
        topic: str,
        evidence_cards: list[EvidenceCard],
    ) -> ReviewOutline:
        """
        生成简单大纲（V25.0 规则版，V25.1 升级为 LLM 大纲生成）。
        按证据类型分组为章节：背景 → 机制 → 事实/方法 → 局限性。
        """
        # 按证据类型分组
        type_groups: dict[EvidenceType, list[EvidenceCard]] = defaultdict(list)
        for c in evidence_cards:
            type_groups[c.evidence_type].append(c)

        sections = []
        order = 0

        # 背景
        if type_groups.get(EvidenceType.BACKGROUND):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="研究背景",
                description="领域背景与研究意义",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.BACKGROUND]],
            ))
            order += 1

        # 机制
        if type_groups.get(EvidenceType.MECHANISM):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="分子机制",
                description="关键分子机制与信号通路",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.MECHANISM]],
            ))
            order += 1

        # 实验事实
        fact_cards = type_groups.get(EvidenceType.FACT, []) + type_groups.get(EvidenceType.CLAIM, [])
        if fact_cards:
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="实验证据",
                description="关键实验结果与数据",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in fact_cards],
            ))
            order += 1

        # 方法
        if type_groups.get(EvidenceType.METHOD):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="研究方法",
                description="主要实验方法与模型系统",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.METHOD]],
            ))
            order += 1

        # 局限性
        if type_groups.get(EvidenceType.LIMITATION):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="研究局限与展望",
                description="现有研究的局限性与未来方向",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.LIMITATION]],
            ))
            order += 1

        # 如果没有任何分组（所有证据都是 fact），创建一个默认章节
        if not sections:
            sections.append(ReviewSection(
                section_id="sec_00",
                title="综述",
                description=f"关于 {topic} 的文献综述",
                order=0,
                assigned_evidence_ids=[c.evidence_id for c in evidence_cards],
            ))

        return ReviewOutline(
            topic=topic,
            sections=sections,
            total_papers=len(set(c.paper_id for c in evidence_cards)),
            total_evidence=len(evidence_cards),
        )

    def _write_draft(
        self,
        topic: str,
        outline: ReviewOutline,
        evidence_dict: dict[str, EvidenceCard],
        review_type: str = "narrative",
        language: str = "en",
    ) -> ReviewDraft:
        """
        撰写综述初稿。V25.0 用 LLM 基于证据卡片写每个章节。
        V25.7: 支持三种综述模板（narrative/comparative/systematic）。
        V25.8: 支持段落级大纲——如果章节有 paragraphs，按段落撰写；否则按章节撰写。
        V25.9: 支持 language 参数（默认英文）。
        """
        all_sentences: list[ReviewSentence] = []
        sent_seq = 0

        for section in outline.sections:
            # V25.8: 如果章节有段落级大纲，按段落撰写；否则按章节撰写（向后兼容）
            if section.paragraphs:
                for paragraph in section.paragraphs:
                    # 收集本段的证据：优先用段落分配的，其次用段落分配论文的证据，最后用章节证据
                    section_evidence = self._collect_paragraph_evidence(paragraph, section, evidence_dict)
                    if not section_evidence:
                        continue

                    # 用 LLM 撰写本段
                    paragraph_text = self._write_paragraph(paragraph, section, section_evidence, review_type=review_type, language=language)

                    # 拆分为句子并关联证据ID
                    sentences = self._split_and_link(
                        paragraph_text, section.section_id, section_evidence, sent_seq
                    )
                    # V25.7: 后处理自动补引用（兜底机制）
                    auto_cited = self._auto_cite_sentences(sentences, section_evidence)
                    if auto_cited > 0:
                        self._auto_cite_count += auto_cited
                    all_sentences.extend(sentences)
                    sent_seq += len(sentences)
            else:
                # 向后兼容：没有段落级大纲时，按章节撰写
                section_evidence = [
                    evidence_dict[eid] for eid in section.assigned_evidence_ids
                    if eid in evidence_dict
                ]
                if not section_evidence:
                    continue

                section_text = self._write_section(section, section_evidence, review_type=review_type, language=language)

                sentences = self._split_and_link(
                    section_text, section.section_id, section_evidence, sent_seq
                )
                auto_cited = self._auto_cite_sentences(sentences, section_evidence)
                if auto_cited > 0:
                    self._auto_cite_count += auto_cited
                all_sentences.extend(sentences)
                sent_seq += len(sentences)

        return ReviewDraft(
            topic=topic,
            outline=outline,
            sentences=all_sentences,
            evidence_cards=evidence_dict,
        )

    def _collect_paragraph_evidence(
        self,
        paragraph: ReviewParagraph,
        section: ReviewSection,
        evidence_dict: dict[str, EvidenceCard],
    ) -> list[EvidenceCard]:
        """
        V25.8: 收集段落的证据。
        V25.9: 增加第四级回退——无明确分配时使用全部证据（确保综述不为空）。
        优先级：段落分配的证据ID > 段落分配论文的证据 > 章节分配的证据 > 全部证据（兜底）
        """
        # 1. 优先用段落直接分配的证据ID
        if paragraph.assigned_evidence_ids:
            evidence = [
                evidence_dict[eid] for eid in paragraph.assigned_evidence_ids
                if eid in evidence_dict
            ]
            if evidence:
                return evidence

        # 2. 其次用段落分配论文的证据
        if paragraph.assigned_paper_ids:
            evidence = [
                card for card in evidence_dict.values()
                if card.paper_id in paragraph.assigned_paper_ids
            ]
            if evidence:
                return evidence

        # 3. 再次用章节分配的证据
        if section.assigned_evidence_ids:
            evidence = [
                evidence_dict[eid] for eid in section.assigned_evidence_ids
                if eid in evidence_dict
            ]
            if evidence:
                return evidence

        # 4. V25.9 兜底：无任何明确分配时，使用全部证据卡片（每段最多 15 条，避免上下文过长）
        # 这确保即使用户没有手动分配论文，综述也能正常生成
        all_evidence = list(evidence_dict.values())
        if len(all_evidence) > 15:
            # 简单策略：均匀采样，避免每段都用完全相同的前15条
            step = max(1, len(all_evidence) // 15)
            return all_evidence[::step][:15]
        return all_evidence

    def _write_paragraph(
        self,
        paragraph: ReviewParagraph,
        section: ReviewSection,
        evidence: list[EvidenceCard],
        review_type: str = "narrative",
        language: str = "en",
    ) -> str:
        """V25.8: 用 LLM 撰写单个段落（基于段落主题和分配的证据）。V25.9: 支持英文/中文。"""
        # 构建证据上下文
        evidence_text = ""
        for card in evidence:
            evidence_text += f"[{card.evidence_id}] ({card.evidence_type.value}) {card.content}\n"
            if card.original_quote:
                evidence_text += f"  Quote: {card.original_quote[:200]}\n"

        # V25.9: 按语言选择 system prompt 和提示文案
        system_prompt = WRITE_SYSTEM_PROMPT_EN if language.lower() == "en" else WRITE_SYSTEM_PROMPT_ZH

        if language.lower() == "en":
            type_hint = {
                "narrative": "Organize by logical threads, progressing layer by layer, telling the research story clearly.",
                "comparative": "Focus on comparing differences between experimental methods, model systems, and conditions; explicitly state which studies used what methods and reached what different conclusions.",
                "systematic": "Maintain methodological rigor, explicitly describe evidence sources and quality, distinguish facts from inferences, emphasize consistency and differences in evidence.",
            }.get(review_type.lower(), "Organize by logical threads, progressing layer by layer.")

            type_label = {
                "narrative": "Narrative Review",
                "comparative": "Comparative Review",
                "systematic": "Systematic Review",
            }.get(review_type.lower(), "Narrative Review")

            user_prompt = (
                f"Review type: {type_label}\n"
                f"Writing style: {type_hint}\n\n"
                f"Section: {section.title}\n"
                f"Paragraph topic: {paragraph.topic}\n"
                f"Paragraph description: {paragraph.description or '(none)'}\n\n"
                f"Available evidence cards:\n{evidence_text}\n\n"
                f"Based on the above evidence cards, write one paragraph of review text (100-200 words) on the topic \"{paragraph.topic}\". "
                f"Every declarative sentence must end with a [evidence_id] citation marker. "
                f"Write only this paragraph's content, no paragraph title, no other paragraphs."
            )
        else:
            type_hint = {
                "narrative": "按逻辑线索组织，层层递进，像讲故事一样把研究脉络讲清楚。",
                "comparative": "重点对比不同实验方法、模型系统和实验条件之间的差异，明确指出哪些研究用了什么方法、得出了什么不同结论。",
                "systematic": "保持方法学严谨性，明确描述证据来源和质量，区分事实和推断，强调证据的一致性和差异性。",
            }.get(review_type.lower(), "按逻辑线索组织，层层递进。")

            type_label = {
                "narrative": "叙事型综述",
                "comparative": "实验对比型综述",
                "systematic": "系统综述型",
            }.get(review_type.lower(), "叙事型综述")

            user_prompt = (
                f"综述模板类型：{type_label}\n"
                f"写作风格要求：{type_hint}\n\n"
                f"所属章节：{section.title}\n"
                f"段落主题：{paragraph.topic}\n"
                f"段落描述：{paragraph.description or '（无）'}\n\n"
                f"可用证据卡片：\n{evidence_text}\n\n"
                f"请根据以上证据卡片，围绕「{paragraph.topic}」这个主题，撰写一段综述正文（100-200字）。"
                f"每个陈述句末尾必须标注 [证据ID] 引用标记。"
                f"只写这一段的内容，不要写段落标题，不要写其他段落。"
            )

        try:
            return self.llm.chat(system_prompt, user_prompt)
        except Exception as e:
            print(f"⚠️  段落撰写失败（{paragraph.paragraph_id}）: {e}")
            return ""

    def _write_section(self, section: ReviewSection, evidence: list[EvidenceCard], review_type: str = "narrative", language: str = "en") -> str:
        """用 LLM 撰写单个章节。V25.7: 根据综述模板类型调整写作风格提示。V25.9: 支持英文/中文。"""
        # 构建证据上下文
        evidence_text = ""
        for card in evidence:
            evidence_text += f"[{card.evidence_id}] ({card.evidence_type.value}) {card.content}\n"
            if card.original_quote:
                evidence_text += f"  Quote: {card.original_quote[:200]}\n"

        # V25.9: 按语言选择 system prompt
        system_prompt = WRITE_SYSTEM_PROMPT_EN if language.lower() == "en" else WRITE_SYSTEM_PROMPT_ZH

        if language.lower() == "en":
            type_hint = {
                "narrative": "Organize by logical threads, progressing layer by layer, telling the research story clearly.",
                "comparative": "Focus on comparing differences between experimental methods, model systems, and conditions.",
                "systematic": "Maintain methodological rigor, explicitly describe evidence sources and quality.",
            }.get(review_type.lower(), "Organize by logical threads, progressing layer by layer.")

            type_label = {
                "narrative": "Narrative Review",
                "comparative": "Comparative Review",
                "systematic": "Systematic Review",
            }.get(review_type.lower(), "Narrative Review")

            user_prompt = (
                f"Review type: {type_label}\n"
                f"Writing style: {type_hint}\n\n"
                f"Section title: {section.title}\n"
                f"Section description: {section.description}\n\n"
                f"Available evidence cards:\n{evidence_text}\n\n"
                f"Based on the above evidence cards, write the review text for this section (200-400 words). "
                f"Every declarative sentence must end with a [evidence_id] citation marker."
            )
        else:
            type_hint = {
                "narrative": "按逻辑线索组织，层层递进，像讲故事一样把研究脉络讲清楚。",
                "comparative": "重点对比不同实验方法、模型系统和实验条件之间的差异，明确指出哪些研究用了什么方法、得出了什么不同结论。",
                "systematic": "保持方法学严谨性，明确描述证据来源和质量，区分事实和推断，强调证据的一致性和差异性。",
            }.get(review_type.lower(), "按逻辑线索组织，层层递进。")

            type_label = {
                "narrative": "叙事型综述",
                "comparative": "实验对比型综述",
                "systematic": "系统综述型",
            }.get(review_type.lower(), "叙事型综述")

            user_prompt = (
                f"综述模板类型：{type_label}\n"
                f"写作风格要求：{type_hint}\n\n"
                f"章节标题：{section.title}\n"
                f"章节描述：{section.description}\n\n"
                f"可用证据卡片：\n{evidence_text}\n\n"
                f"请根据以上证据卡片，撰写本章节的综述正文（200-400字）。"
                f"每个陈述句末尾必须标注 [证据ID] 引用标记。"
            )

        try:
            return self.llm.chat(system_prompt, user_prompt)
        except LLMError as e:
            print(f"⚠️  章节 {section.title} 撰写失败: {e}")
            # 降级：直接用证据卡片内容拼接
            return "\n".join(f"- {c.content} [{c.evidence_id}]" for c in evidence)

    def _split_and_link(
        self,
        text: str,
        section_id: str,
        evidence: list[EvidenceCard],
        start_seq: int,
    ) -> list[ReviewSentence]:
        """
        将 LLM 输出的章节文本拆分为句子，并关联证据ID。
        解析文本中的 [ev_xxx] 标记作为证据关联。
        """
        import re

        sentences: list[ReviewSentence] = []
        # 按句号/问号/感叹号拆分（保留标点）
        raw_sents = re.split(r'(?<=[。！？.!?])\s*', text)
        valid_evidence_ids = {c.evidence_id for c in evidence}

        for i, raw in enumerate(raw_sents):
            raw = raw.strip()
            if not raw or len(raw) < 5:
                continue

            # 提取句子中的证据ID标记
            found_ids = re.findall(r'\[(ev_[^\]]+)\]', raw)
            # 过滤掉不存在的ID
            linked_ids = [eid for eid in found_ids if eid in valid_evidence_ids]

            # 清理文本中的引用标记（输出时再加回）
            clean_text = re.sub(r'\[ev_[^\]]+\]', '', raw).strip()
            if not clean_text:
                continue

            sentences.append(ReviewSentence(
                sentence_id=f"sent_{section_id}_{start_seq + i}",
                section_id=section_id,
                text=clean_text,
                evidence_ids=linked_ids,
            ))

        return sentences

    # ──────────────────────────────────────────────
    # V25.7: 后处理自动补引用（兜底机制）
    # ──────────────────────────────────────────────

    def _auto_cite_sentences(
        self,
        sentences: list[ReviewSentence],
        section_evidence: list[EvidenceCard],
        min_overlap: int = 2,
    ) -> int:
        """
        对无引用的句子，从同章节证据卡片中自动匹配最相关的，补上引用标记。

        匹配策略：字符级 2-gram 关键词重叠（对中英文均适用，无需分词）。
        阈值：至少 min_overlap 个 2-gram 重叠才补，否则保持无引用（会被校验拒绝）。

        Args:
            sentences: 本章节的句子列表（会原地修改 evidence_ids 和 verification_note）
            section_evidence: 本章节可用的证据卡片列表
            min_overlap: 最小关键词重叠数阈值，默认 2

        Returns:
            自动补引用的句子数量
        """
        if not sentences or not section_evidence:
            return 0

        # 预计算每个证据卡片的 2-gram 集合（content + original_quote）
        evidence_ngrams: list[tuple[str, set[str]]] = []
        for card in section_evidence:
            text = card.content or ""
            if card.original_quote:
                text += " " + card.original_quote
            ngrams = self._extract_2grams(text)
            if ngrams:
                evidence_ngrams.append((card.evidence_id, ngrams))

        if not evidence_ngrams:
            return 0

        auto_cited = 0
        for sent in sentences:
            # 只处理无引用的句子
            if sent.evidence_ids:
                continue

            sent_ngrams = self._extract_2grams(sent.text)
            if not sent_ngrams:
                continue

            # 找重叠最多的证据卡片
            best_eid = None
            best_overlap = 0
            for eid, e_ngrams in evidence_ngrams:
                overlap = len(sent_ngrams & e_ngrams)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_eid = eid

            # 达到阈值才补
            if best_eid and best_overlap >= min_overlap:
                sent.evidence_ids = [best_eid]
                sent.verification_note = f"自动补引用: {best_eid}（关键词重叠数={best_overlap}，建议人工复核）"
                auto_cited += 1

        return auto_cited

    @staticmethod
    def _extract_2grams(text: str) -> set[str]:
        """
        从文本中提取字符级 2-gram 集合（对中英文均适用，无需分词）。
        转小写，去除标点和空白，只保留字母、数字、中文字符。

        例如："STAT1在IFN-gamma刺激下被磷酸化" → {"st","ta","a1","1在","在i","if","fn","n-",...}
        """
        import re

        if not text:
            return set()

        # 转小写，只保留字母、数字、中文字符
        cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '', text.lower())
        if len(cleaned) < 2:
            return set()

        # 提取所有连续2个字符的组合
        return {cleaned[i:i+2] for i in range(len(cleaned) - 1)}

    @staticmethod
    def _format_ref_numbers(numbers: list[int]) -> str:
        """
        V25.18: 格式化参考文献编号，支持连续编号合并。

        例如：
        - [1, 2, 3] → "[1-3]"
        - [1, 3, 5] → "[1,3,5]"
        - [1, 2, 4, 5, 6] → "[1-2,4-6]"
        - [1] → "[1]"
        """
        if not numbers:
            return ""

        sorted_nums = sorted(set(numbers))
        if len(sorted_nums) == 1:
            return f"[{sorted_nums[0]}]"

        # 合并连续编号
        ranges = []
        start = sorted_nums[0]
        end = sorted_nums[0]

        for n in sorted_nums[1:]:
            if n == end + 1:
                end = n
            else:
                ranges.append((start, end))
                start = n
                end = n
        ranges.append((start, end))

        # 格式化每个区间
        parts = []
        for s, e in ranges:
            if s == e:
                parts.append(str(s))
            else:
                parts.append(f"{s}-{e}")

        return "[" + ",".join(parts) + "]"

    def _render_markdown(
        self,
        topic: str,
        draft: ReviewDraft,
        evidence_dict: dict[str, EvidenceCard],
        conflicts: Optional[list] = None,
        paper_metadata_map: Optional[dict[str, PaperMetadata]] = None,
        citation_style: str = "apa",
        language: str = "en",
    ) -> str:
        """将校验后的 draft 渲染为 Markdown。V25.3: 含研究争议章节。V25.7: 多格式参考文献格式化。V25.9: 支持英文/中文标题。V25.18: 正文引用从证据ID改为参考文献编号，按出现顺序编号。"""
        lines = [f"# {topic}", ""]

        # V25.18: 建立 evidence_id → 参考文献编号映射（按正文首次出现顺序）
        evidence_to_ref = {}  # evidence_id -> ref_number
        paper_to_ref = {}     # paper_id -> ref_number
        ref_paper_ids_ordered = []  # 按出现顺序排列的 paper_id
        ref_counter = 0

        for section in draft.outline.sections:
            section_sents = draft.sentences_by_section(section.section_id)
            valid_sents = [
                s for s in section_sents
                if s.status in (SentenceStatus.VERIFIED, SentenceStatus.CONTROVERSIAL)
            ]
            for sent in valid_sents:
                for eid in sent.evidence_ids:
                    if eid in evidence_dict and eid not in evidence_to_ref:
                        pid = (evidence_dict[eid].paper_id or "").strip()
                        if pid:
                            if pid not in paper_to_ref:
                                ref_counter += 1
                                paper_to_ref[pid] = ref_counter
                                ref_paper_ids_ordered.append(pid)
                            evidence_to_ref[eid] = paper_to_ref[pid]

        # V25.18: 把研究争议中引用的 evidence_id 也加入映射
        if conflicts:
            for conflict in conflicts:
                for side in getattr(conflict, 'sides', []) or []:
                    for eid in side.get('evidence_ids', []) or []:
                        if eid in evidence_dict and eid not in evidence_to_ref:
                            pid = (evidence_dict[eid].paper_id or "").strip()
                            if pid:
                                if pid not in paper_to_ref:
                                    ref_counter += 1
                                    paper_to_ref[pid] = ref_counter
                                    ref_paper_ids_ordered.append(pid)
                                evidence_to_ref[eid] = paper_to_ref[pid]

        for section in draft.outline.sections:
            section_sents = draft.sentences_by_section(section.section_id)
            # 只保留已验证和有争议的句子，剔除被拒绝的
            valid_sents = [
                s for s in section_sents
                if s.status in (SentenceStatus.VERIFIED, SentenceStatus.CONTROVERSIAL)
            ]
            if not valid_sents:
                continue

            lines.append(f"## {section.title}")
            lines.append("")

            for sent in valid_sents:
                line = sent.text
                # V25.18: 把证据 ID 引用转换成参考文献编号
                if sent.evidence_ids:
                    ref_numbers = sorted(set(
                        evidence_to_ref[eid] for eid in sent.evidence_ids
                        if eid in evidence_to_ref
                    ))
                    if ref_numbers:
                        citation_str = self._format_ref_numbers(ref_numbers)
                        line = f"{line} {citation_str}"
                if sent.status == SentenceStatus.CONTROVERSIAL:
                    controversial_label = "⚠️ (controversial)" if language.lower() == "en" else "⚠️（存在争议）"
                    line = f"{line} {controversial_label}"
                lines.append(line)
                lines.append("")

        # V25.5: 研究争议章节（区分真正矛盾和条件差异型，生成两个章节）
        if conflicts:
            # 分组
            true_controversies = [c for c in conflicts if getattr(c, 'conflict_type', 'true_controversy') == 'true_controversy']
            condition_differences = [c for c in conflicts if getattr(c, 'conflict_type', 'true_controversy') == 'condition_difference']

            if language.lower() == "en":
                # 章节1：真正矛盾
                if true_controversies:
                    lines.append("## Research Controversies and Inconsistencies")
                    lines.append("")
                    for i, conflict in enumerate(true_controversies, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**Experimental condition difference analysis**: {conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**Viewpoints from all sides**:")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', 'Viewpoint')}: {side.get('claim', '')} {eids}")
                            lines.append("")

                # 章节2：条件差异型
                if condition_differences:
                    lines.append("## Result Differences Under Different Experimental Conditions")
                    lines.append("")
                    lines.append("The following result differences primarily arise from variations in experimental conditions (e.g., mutation type, cell type, measurement endpoint, stimulus conditions), rather than genuine academic controversy.")
                    lines.append("")
                    for i, conflict in enumerate(condition_differences, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**Condition difference analysis**: {conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**Results under each condition**:")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', 'Condition')}: {side.get('claim', '')} {eids}")
                            lines.append("")
            else:
                # 中文标题（向后兼容）
                if true_controversies:
                    lines.append("## 研究争议与不一致")
                    lines.append("")
                    for i, conflict in enumerate(true_controversies, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**实验条件差异分析**：{conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**各方观点**：")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', '观点')}：{side.get('claim', '')} {eids}")
                            lines.append("")

                if condition_differences:
                    lines.append("## 不同实验条件下的结果差异")
                    lines.append("")
                    lines.append("以下结果差异主要源于实验条件的不同（如突变类型、细胞类型、测量指标、刺激条件等），并非真正的学术争议。")
                    lines.append("")
                    for i, conflict in enumerate(condition_differences, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**条件差异分析**：{conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**各条件下的结果**：")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', '条件')}：{side.get('claim', '')} {eids}")
                            lines.append("")

        # 参考文献（V25.7: CSL 引擎渲染，专业样式，零幻觉。V25.18: 按正文出现顺序编号）
        refs_title = "## References" if language.lower() == "en" else "## 参考文献"
        lines.append(refs_title)
        lines.append("")

        # V25.18: 使用按正文出现顺序排列的 paper_id（前面已建立 ref_paper_ids_ordered）
        # 如果没有（极端情况），回退到从 evidence_dict 收集
        if not ref_paper_ids_ordered:
            seen_pids = set()
            for card in evidence_dict.values():
                pid = (card.paper_id or "").strip()
                if pid and pid not in seen_pids:
                    seen_pids.add(pid)
                    ref_paper_ids_ordered.append(pid)

        # 按出现顺序收集元数据
        ref_metadata_list = []
        if paper_metadata_map:
            for pid in ref_paper_ids_ordered:
                if pid in paper_metadata_map:
                    ref_metadata_list.append(paper_metadata_map[pid])

        # 用 CSL 引擎批量渲染
        if ref_metadata_list:
            try:
                formatted_refs = format_citation_list(ref_metadata_list, style=citation_style)
                for i, ref_str in enumerate(formatted_refs, 1):
                    # V25.18: 加编号前缀，和正文引用对应
                    lines.append(f"{i}. {ref_str}")
            except Exception as e:
                # CSL 引擎渲染失败，降级为简单格式
                print(f"⚠️  CSL 引擎渲染失败，降级为简单格式: {e}")
                for i, pid in enumerate(ref_paper_ids_ordered, 1):
                    card = next((c for c in evidence_dict.values() if c.paper_id == pid), None)
                    title = card.paper_title if card else pid
                    lines.append(f"{i}. [{pid}] {title}")
        else:
            # 没有元数据，用简单格式
            for i, pid in enumerate(ref_paper_ids_ordered, 1):
                card = next((c for c in evidence_dict.values() if c.paper_id == pid), None)
                title = card.paper_title if card else pid
                lines.append(f"{i}. [{pid}] {title}")

        lines.append("")

        return "\n".join(lines)

    def _fetch_paper_metadata(self, evidence_cards: list[EvidenceCard]) -> dict[str, PaperMetadata]:
        """
        从数据库查询论文元数据，用于 GB/T 7714 参考文献格式化（V25.7）。

        返回：{paper_id: PaperMetadata} 字典
        """
        metadata_map = {}
        if not self.db_path or not Path(self.db_path).exists():
            return metadata_map

        # 收集所有需要查询的 paper_id
        paper_ids = set()
        for card in evidence_cards:
            pid = (card.paper_id or "").strip()
            if pid:
                paper_ids.add(pid)

        if not paper_ids:
            return metadata_map

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 批量查询（SQLite 对 IN 子句的参数数量有限制，这里分批处理）
            pid_list = list(paper_ids)
            batch_size = 500
            for i in range(0, len(pid_list), batch_size):
                batch = pid_list[i:i + batch_size]
                placeholders = ",".join("?" * len(batch))
                cursor.execute(
                    f"SELECT paper_id, title, authors, journal, year, doi FROM papers WHERE paper_id IN ({placeholders})",
                    batch
                )
                for row in cursor.fetchall():
                    metadata = build_metadata_from_db_row(dict(row))
                    metadata_map[metadata.paper_id] = metadata

            conn.close()
        except Exception as e:
            # 数据库查询失败时静默降级，不影响主流程
            print(f"⚠️  查询论文元数据失败（将使用简单格式）: {e}")

        return metadata_map

    def _build_references(self, evidence_cards: list[EvidenceCard], paper_metadata_map: Optional[dict[str, PaperMetadata]] = None, citation_style: str = "apa") -> list[dict]:
        """构建参考文献列表（V25.1: 过滤空 paper_id；V25.7: CSL引擎格式化字符串）。"""
        seen = set()
        refs = []
        metadata_list = []

        for card in evidence_cards:
            pid = (card.paper_id or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            ref_entry = {
                "paper_id": pid,
                "title": card.paper_title or pid,
                "section": card.section_l1,
            }
            refs.append(ref_entry)
            if paper_metadata_map and pid in paper_metadata_map:
                metadata_list.append(paper_metadata_map[pid])
                # 检查缺失字段
                missing = get_missing_fields_report(paper_metadata_map[pid])
                if missing:
                    ref_entry["missing_fields"] = missing

        # 用 CSL 引擎批量渲染格式化字符串
        if metadata_list:
            try:
                formatted_refs = format_citation_list(metadata_list, style=citation_style)
                for i, ref_entry in enumerate(refs):
                    if i < len(formatted_refs):
                        ref_entry["formatted"] = formatted_refs[i]
            except Exception as e:
                print(f"⚠️  CSL 引擎渲染参考文献失败: {e}")

        return refs


# ──────────────────────────────────────────────
# 自测（不依赖 LLM 和检索，测试数据结构和渲染）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("📝 Review Generator Test (V25.0)")
    print("=" * 60)

    # 构造测试证据
    cards = [
        EvidenceCard(
            evidence_id="ev_p1_para1_0",
            paper_id="paper1",
            para_id="para1",
            paper_title="STAT1 and interferon immunity",
            content="STAT1 is phosphorylated at Y701 by JAK kinases in response to IFN-gamma.",
            evidence_type=EvidenceType.MECHANISM,
        ),
        EvidenceCard(
            evidence_id="ev_p1_para2_0",
            paper_id="paper1",
            para_id="para2",
            paper_title="STAT1 and interferon immunity",
            content="STAT1 forms homodimers (GAF) that bind GAS elements to induce target gene transcription.",
            evidence_type=EvidenceType.MECHANISM,
        ),
        EvidenceCard(
            evidence_id="ev_p2_para1_0",
            paper_id="paper2",
            para_id="para1",
            paper_title="JAK-STAT pathway in disease",
            content="STAT1 knockout mice are highly susceptible to viral and mycobacterial infections.",
            evidence_type=EvidenceType.FACT,
        ),
    ]

    # 测试简单大纲生成
    print("\n--- 简单大纲生成测试 ---")
    # 创建一个无 LLM、无检索的 generator（只测试大纲和渲染）
    generator = ReviewGenerator.__new__(ReviewGenerator)
    generator.max_evidence_per_paper = 5
    generator.use_llm_verification = False

    outline = generator._generate_simple_outline("STAT1 干扰素调控", cards)
    print(f"  主题: {outline.topic}")
    print(f"  章节数: {len(outline.sections)}")
    for sec in outline.sections:
        print(f"    [{sec.section_id}] {sec.title} ({len(sec.assigned_evidence_ids)} 条证据)")

    # 测试 Markdown 渲染
    print("\n--- Markdown 渲染测试 ---")
    evidence_dict = {c.evidence_id: c for c in cards}

    # 构造一个模拟 draft
    from .models import ReviewSentence, SentenceStatus
    test_draft = ReviewDraft(
        topic="STAT1 干扰素调控",
        outline=outline,
        sentences=[
            ReviewSentence(
                sentence_id="sent_sec_00_0",
                section_id="sec_00",
                text="STAT1 在 IFN-gamma 刺激下被 JAK 激酶磷酸化于 Y701 位点。",
                evidence_ids=["ev_p1_para1_0"],
                status=SentenceStatus.VERIFIED,
            ),
            ReviewSentence(
                sentence_id="sent_sec_00_1",
                section_id="sec_00",
                text="磷酸化的 STAT1 形成同源二聚体 GAF，结合 GAS 元件诱导靶基因转录。",
                evidence_ids=["ev_p1_para2_0"],
                status=SentenceStatus.VERIFIED,
            ),
            ReviewSentence(
                sentence_id="sent_sec_01_0",
                section_id="sec_01",
                text="STAT1 敲除小鼠对病毒和分枝杆菌感染高度易感。",
                evidence_ids=["ev_p2_para1_0"],
                status=SentenceStatus.VERIFIED,
            ),
            ReviewSentence(
                sentence_id="sent_sec_01_1",
                section_id="sec_01",
                text="这是一句编造的无证据结论。",
                evidence_ids=[],
                status=SentenceStatus.REJECTED,
                verification_note="无证据ID",
            ),
        ],
        evidence_cards=evidence_dict,
    )

    markdown = generator._render_markdown("STAT1 干扰素调控", test_draft, evidence_dict)
    print(markdown[:800])
    print("...")

    # 测试句子拆分和证据关联
    print("\n--- 句子拆分与证据关联测试 ---")
    test_text = "STAT1 is phosphorylated at Y701 [ev_p1_para1_0]. It forms GAF dimers [ev_p1_para2_0]. Knockout mice are susceptible [ev_p2_para1_0]."
    split_sents = generator._split_and_link(test_text, "sec_00", cards, 0)
    for s in split_sents:
        print(f"  [{s.sentence_id}] evidence={s.evidence_ids} — {s.text[:50]}")

    print("\n✅ 数据结构和渲染测试通过。")
    print("   完整生成流程需要 Ollama 服务 + 检索层运行。")
    print("   启动后可通过 API: POST /api/review/generate")


# ──────────────────────────────────────────────
# V26.1: 自动发配论文到章节
# ──────────────────────────────────────────────

def assign_papers_to_outline(
    outline: dict,
    papers: list[dict],
    evidence_cards: Optional[list[dict]] = None,
) -> dict:
    """V26.1: 自动计算每篇论文与各章节的相似度，把论文发配到相关章节。

    简单版本：用关键词匹配计算相似度，把论文发配到最相关的章节。

    Args:
        outline: 大纲 JSON {"sections": [...]}
        papers: 论文列表 [{"paper_id": ..., "title": ..., ...}]
        evidence_cards: 证据卡片列表（可选，用于更精确的匹配）

    Returns:
        更新后的大纲（每章节包含 assigned_paper_ids）
    """
    if not outline or not outline.get("sections"):
        return outline

    if not papers:
        return outline

    # 1. 收集每个章节的关键词
    section_keywords = {}
    for sec in outline["sections"]:
        sec_text = sec.get("title", "") + " " + sec.get("description", "")
        for para in sec.get("paragraphs", []):
            sec_text += " " + para.get("topic", "") + " " + para.get("description", "")
        # 简单分词（按空格和标点）
        keywords = set(sec_text.lower().split())
        section_keywords[sec["section_id"]] = keywords

    # 2. 为每篇论文计算与每个章节的相似度
    assignments = {}  # paper_id -> section_id
    for paper in papers:
        pid = paper.get("paper_id", "")
        title = paper.get("title", "")
        if not pid:
            continue

        # 论文的关键词（标题简单分词）
        paper_keywords = set(title.lower().split())

        # 计算与每个章节的相似度（关键词重叠数）
        best_section = None
        best_score = 0
        for sec_id, sec_keywords in section_keywords.items():
            overlap = len(paper_keywords & sec_keywords)
            if overlap > best_score:
                best_score = overlap
                best_section = sec_id

        # 如果没有匹配到任何章节，发配到第一个章节
        if best_section is None:
            best_section = outline["sections"][0]["section_id"]

        assignments[pid] = best_section

    # 3. 更新大纲的 assigned_paper_ids
    for sec in outline["sections"]:
        sec_id = sec["section_id"]
        sec_papers = [pid for pid, sid in assignments.items() if sid == sec_id]
        sec["assigned_paper_ids"] = sec_papers

        # 段落级分配：按段落关键词匹配
        for para in sec.get("paragraphs", []):
            para_text = para.get("topic", "") + " " + para.get("description", "")
            para_keywords = set(para_text.lower().split())

            para_papers = []
            for pid in sec_papers:
                paper = next((p for p in papers if p.get("paper_id") == pid), None)
                if not paper:
                    continue
                title = paper.get("title", "")
                paper_keywords = set(title.lower().split())
                overlap = len(paper_keywords & para_keywords)
                if overlap > 0:
                    para_papers.append(pid)

            para["assigned_paper_ids"] = para_papers

    return outline
