"""
V25.0 - 证据抽取 Agent（EvidenceExtractor）。

核心防幻觉模块：从检索到的段落中抽取结构化 EvidenceCard，
每条证据强制绑定 paper_id + para_id，可反向溯源到 PDF 原文。

铁律：任何结论，没有 EvidenceCard 就禁止写入综述正文。

用法:
    extractor = EvidenceExtractor(llm_client)
    cards = extractor.extract_from_paragraphs(paragraphs, topic="STAT1 干扰素调控")
"""

from __future__ import annotations

import re
from typing import Optional

from .llm_client import LLMClient, LLMError
from .models import EvidenceCard, EvidenceType


# ──────────────────────────────────────────────
# Prompt 模板（V25.9: 英文默认，保留中文向后兼容）
# ──────────────────────────────────────────────

SYSTEM_PROMPT_EN = """You are a scientific literature evidence extractor. Your task is to extract structured evidence cards from the given academic paper paragraphs.

Strict rules:
1. Only extract from the given paragraphs — never fabricate information not present in the text
2. Each evidence must be content explicitly stated in the paragraph, not your speculation
3. If the paragraph is a reference list, acknowledgments, copyright notice, or other non-body content, return an empty list
4. The original_quote for each evidence must be an original sentence from the paragraph (may be truncated but not paraphrased, **max 200 characters**)
5. evidence_type can only be: fact / mechanism / claim / method / limitation / background
6. Extract at most 3 evidence cards per paragraph, only the most important ones

【Experimental condition labels — must be filled carefully, this is critical for downstream conflict detection】
For each evidence, extract the following condition labels from the original text whenever possible. If not mentioned in the text, fill in "unknown" — never fabricate:
- mutation_type: Mutation type, choose the closest from: GOF (gain-of-function mutation) / LOF (loss-of-function mutation/knockout/deficiency) / specific site mutation (e.g., Q124H/Y701F) / not applicable (normal physiological state, non-mutation study) / unknown
- cell_type: Cell/sample type, e.g.: monocytes / T cells / B cells / fibroblasts / epithelial cells / cell line name (e.g., HEK293/HeLa) / mouse model / human patients / unknown
- measurement: Measurement endpoint, choose the closest from: mRNA level / total protein level / phosphorylated protein level / DNA binding activity / transcriptional activity / functional assay (e.g., infection susceptibility) / clinical phenotype / unknown
- stimulus: Stimulus/treatment condition, e.g.: IFN-α stimulation / IFN-gamma stimulation / IL-27 stimulation / viral infection / unstimulated (baseline) / unknown

Output format: strictly a JSON array, each element containing:
- content: Evidence content (summarize in your own words, but do not change the original meaning) — **write in English**
- original_quote: Original quote from the text
- evidence_type: Evidence type
- model_system: Experimental model (empty string if not mentioned)
- sample_size: Sample size (empty string if not mentioned)
- treatment: Treatment condition (empty string if not mentioned)
- time_point: Time point (empty string if not mentioned)
- mutation_type: Mutation type (GOF/LOF/specific site mutation/not applicable/unknown)
- cell_type: Cell type
- measurement: Measurement endpoint
- stimulus: Stimulus condition

Return only the JSON array, no explanatory text."""

SYSTEM_PROMPT_ZH = """你是一个科研文献证据抽取器。你的任务是从给定的学术论文段落中，抽取结构化的证据卡片。

严格规则：
1. 只从给定段落中抽取，绝对不能编造段落中没有的信息
2. 每条证据必须是段落中明确陈述的内容，不能是你的推测
3. 如果段落是参考文献列表、致谢、版权声明等非正文内容，返回空列表
4. 每条证据的 original_quote 必须是段落中的原文句子（可适当截断，但不能改写，**不超过200字**）
5. evidence_type 只能是: fact / mechanism / claim / method / limitation / background
6. 每个段落最多抽取 3 条证据，只抽最重要的

【实验条件标签 — 必须认真填写，这是后续冲突检测的关键】
每条证据都要尽可能从原文中提取以下条件标签，如果原文没提，填 "未知"，绝对不要编造：
- mutation_type: 突变类型，从以下选项选最接近的：GOF(功能获得性突变) / LOF(功能丧失性突变/敲除/缺陷) / 特定位点突变(如Q124H/Y701F等) / 不适用(正常生理状态，非突变研究) / 未知
- cell_type: 细胞/样本类型，如：单核细胞 / T细胞 / B细胞 / 成纤维细胞 / 上皮细胞 / 细胞系名称(如HEK293/HeLa) / 小鼠模型 / 人类患者 / 未知
- measurement: 测量指标，从以下选项选最接近的：mRNA水平 / 总蛋白水平 / 磷酸化蛋白水平 / DNA结合活性 / 转录活性 / 功能实验(如感染易感性) / 临床表型 / 未知
- stimulus: 刺激/处理条件，如：IFN-α刺激 / IFN-gamma刺激 / IL-27刺激 / 病毒感染 / 未刺激(基线状态) / 未知

输出格式：严格的 JSON 数组，每个元素包含：
- content: 证据内容（用自己的话概括，但不能改变原意）
- original_quote: 原文引用
- evidence_type: 证据类型
- model_system: 实验模型（如未提及则为空字符串）
- sample_size: 样本量（如未提及则为空字符串）
- treatment: 处理条件（如未提及则为空字符串）
- time_point: 时间点（如未提及则为空字符串）
- mutation_type: 突变类型（GOF/LOF/特定位点突变/不适用/未知）
- cell_type: 细胞类型
- measurement: 测量指标
- stimulus: 刺激条件

只返回 JSON 数组，不要任何解释文字。"""

# 默认使用英文
SYSTEM_PROMPT = SYSTEM_PROMPT_EN


# ──────────────────────────────────────────────
# 证据抽取器
# ──────────────────────────────────────────────

class EvidenceExtractor:
    """
    从检索段落中抽取结构化证据卡片。

    Args:
        llm_client: LLMClient 实例
        max_evidence_per_paragraph: 每个段落最多抽取的证据数，默认 3
        min_paragraph_length: 段落最小长度（字符），低于此值跳过，默认 50
    """

    def __init__(
        self,
        llm_client: LLMClient,
        max_evidence_per_paragraph: int = 3,
        min_paragraph_length: int = 50,
    ):
        self.llm = llm_client
        self.max_evidence_per_paragraph = max_evidence_per_paragraph
        self.min_paragraph_length = min_paragraph_length
        # V25.2: 句内定位器（抽取后自动定位 original_quote 在段落中的偏移）
        from .sentence_locator import SentenceLocator
        self._locator = SentenceLocator()
        # V31.7: 缓存改成存在硬盘上（JSON 文件），重启不丢失
        import json
        import os
        self._cache_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "evidence_cache.json")
        self._cache: dict[str, list[EvidenceCard]] = {}
        # 从硬盘加载缓存
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                print(f"📦 从硬盘加载了 {len(self._cache)} 条缓存")
            except Exception as e:
                print(f"⚠️ 加载缓存失败：{e}")
                self._cache = {}

    def _save_cache_to_disk(self):
        """V31.7: 把缓存保存到硬盘。"""
        import json
        import os
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存缓存失败：{e}")

    def _get_cache_key(self, para: dict) -> str:
        """V30.6: 生成缓存 key。"""
        return f"{para.get('paper_id', '')}_{para.get('para_id', '')}"

    def extract_from_paragraphs(
        self,
        paragraphs: list[dict],
        topic: str = "",
        language: str = "en",
    ) -> list[EvidenceCard]:
        """
        从一组检索段落中抽取证据卡片。

        Args:
            paragraphs: 段落列表，每个 dict 需含 para_id, paper_id, text,
                       可选 section_l1, page, paper_title
            topic: 综述主题（用于指导抽取方向，可选）
            language: V25.9: 证据内容语言，"en"（默认，英文）或 "zh"（中文）

        Returns:
            EvidenceCard 列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # V30.1: 先过滤掉不需要处理的段落
        valid_paragraphs = []
        for para in paragraphs:
            text = para.get("text", "").strip()
            if len(text) < self.min_paragraph_length:
                continue
            if self._is_boilerplate(text):
                continue
            valid_paragraphs.append(para)

        # V30.6: 检查缓存，把已经处理过的段落直接拿出来
        cached_cards: list[EvidenceCard] = []
        paragraphs_to_process: list[dict] = []
        cache_hits = 0

        for para in valid_paragraphs:
            cache_key = self._get_cache_key(para)
            if cache_key in self._cache:
                cached_cards.extend(self._cache[cache_key])
                cache_hits += 1
            else:
                paragraphs_to_process.append(para)

        if cache_hits > 0:
            print(f"📦 缓存命中：{cache_hits} 个段落，直接从缓存读取")

        # V30.3: 批量处理，5 段一组
        batch_size = 5
        batches = [paragraphs_to_process[i:i+batch_size] for i in range(0, len(paragraphs_to_process), batch_size)]

        print(f"🔍 批量证据抽取：{len(paragraphs_to_process)} 个段落待处理，{len(batches)} 批，每批 {batch_size} 段")

        all_cards: list[EvidenceCard] = cached_cards  # V30.6: 先把缓存里的结果放进去
        seq_counter = len(cached_cards)

        # V31.10: 熔断机制 - 失败太多就直接停止
        failed_count = 0
        max_failed = 10  # 最多失败 10 次就停止
        stopped = False

        # V30.3: 并行处理批次
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 提交所有批次
            future_to_batch = {}
            for i, batch in enumerate(batches):
                future = executor.submit(
                    self._extract_batch,
                    batch,
                    topic,
                    language=language,
                )
                future_to_batch[future] = (i, batch)

            # 收集结果
            for future in as_completed(future_to_batch):
                if stopped:
                    continue
                batch_idx, batch = future_to_batch[future]
                try:
                    cards = future.result()
                    all_cards.extend(cards)
                    seq_counter += len(cards)
                except LLMError as e:
                    failed_count += 1
                    print(f"⚠️  第 {batch_idx+1} 批证据抽取失败: {e}")
                    # V31.10: 失败太多就停止
                    if failed_count >= max_failed:
                        print(f"⚠️  失败次数达到 {max_failed}，停止证据抽取，跳过剩余批次")
                        stopped = True
                        continue
                    # V30.3: 批量失败后，退回到单段处理
                    for para in batch:
                        try:
                            cards = self._extract_one_paragraph(para, topic, 0, language=language)
                            all_cards.extend(cards)
                            seq_counter += len(cards)
                        except LLMError as e2:
                            print(f"⚠️  段落 {para.get('para_id', '?')} 单段抽取也失败: {e2}")

        # V31.7: 把缓存保存到硬盘，重启不丢失
        self._save_cache_to_disk()

        return all_cards

    def _extract_batch(
        self,
        batch: list[dict],
        topic: str,
        language: str = "en",
    ) -> list[EvidenceCard]:
        """V30.3: 批量从多个段落抽取证据。"""
        # 构建批量 prompt
        paragraphs_text = ""
        for i, para in enumerate(batch):
            paragraphs_text += f"【段落 {i+1}】(para_id: {para['para_id']}, paper_id: {para['paper_id']})\n"
            paragraphs_text += para["text"][:2000]  # 每段最多 2000 字
            paragraphs_text += "\n\n"

        user_prompt = f"""Topic: {topic}

{paragraphs_text}

Extract evidence cards from each paragraph above. 
For each paragraph, extract at most 3 evidence cards.
Return a JSON object with keys "paragraph_1", "paragraph_2", ..., each value is an array of evidence cards.
If a paragraph has no evidence, return an empty array for that key.
"""

        # V25.9: 按语言选择 system prompt
        system_prompt = SYSTEM_PROMPT_EN if language.lower() == "en" else SYSTEM_PROMPT_ZH

        raw_results = self.llm.chat_json(system_prompt, user_prompt)

        # V30.3: 解析批量结果
        all_cards: list[EvidenceCard] = []
        seq_counter = 0

        # V30.7: 编号核查，看看哪些段落的结果缺失了
        missing_paragraphs: list[dict] = []

        if isinstance(raw_results, dict):
            for i, para in enumerate(batch):
                para_key = f"paragraph_{i+1}"
                para_results = raw_results.get(para_key, [])
                if not isinstance(para_results, list):
                    para_results = []
                    missing_paragraphs.append(para)  # V30.7: 标记为缺失
                    continue

                para_cards: list[EvidenceCard] = []  # V30.6: 这个段落的证据卡片

                for item in para_results[:self.max_evidence_per_paragraph]:
                    if not isinstance(item, dict):
                        continue

                    content = item.get("content", "").strip()
                    if not content:
                        continue

                    evidence_type = self._parse_evidence_type(item.get("evidence_type", "fact"))

                    safe_paper = self._sanitize_id(para["paper_id"])
                    safe_para = self._sanitize_id(para["para_id"])

                    card = EvidenceCard(
                        evidence_id=f"ev_{safe_paper}_{safe_para}_{seq_counter}",
                        seq=seq_counter,
                        content=content,
                        evidence_type=evidence_type,
                        original_quote=item.get("original_quote", "")[:500],
                        paper_id=para["paper_id"],
                        para_id=para["para_id"],
                        section_l1=para.get("section_l1", ""),
                        page=para.get("page", 0),
                        paper_title=para.get("paper_title", ""),
                        model_system=item.get("model_system", ""),
                        sample_size=item.get("sample_size", ""),
                        treatment=item.get("treatment", ""),
                        time_point=item.get("time_point", ""),
                        mutation_type=item.get("mutation_type", "unknown"),
                        cell_type=item.get("cell_type", "unknown"),
                        measurement=item.get("measurement", "unknown"),
                        stimulus=item.get("stimulus", "unknown"),
                        confidence=item.get("confidence", 1.0),
                    )
                    all_cards.append(card)
                    para_cards.append(card)  # V30.6: 加到这个段落的列表里
                    seq_counter += 1

                # V30.6: 把这个段落的证据卡片存到缓存里
                cache_key = self._get_cache_key(para)
                self._cache[cache_key] = para_cards

        # V30.7: 补缺失的段落，不重发整批，只单独补
        if missing_paragraphs:
            print(f"⚠️  批量结果缺失 {len(missing_paragraphs)} 个段落，单独补一下")
            for para in missing_paragraphs:
                try:
                    cards = self._extract_one_paragraph(para, topic, seq_counter, language=language)
                    all_cards.extend(cards)
                    seq_counter += len(cards)
                    # 也存到缓存里
                    cache_key = self._get_cache_key(para)
                    self._cache[cache_key] = cards
                except LLMError as e:
                    print(f"⚠️  段落 {para.get('para_id', '?')} 单独补也失败: {e}")

        # V31.7: 把缓存保存到硬盘，重启不丢失
        self._save_cache_to_disk()

        return all_cards

    def _extract_one_paragraph(
        self,
        para: dict,
        topic: str,
        start_seq: int,
        language: str = "en",
    ) -> list[EvidenceCard]:
        """从单个段落抽取证据。V25.9: 支持英文/中文 prompt。"""
        para_id = para["para_id"]
        paper_id = para["paper_id"]
        text = para["text"]

        user_prompt = self._build_user_prompt(text, topic, language=language)

        # V25.9: 按语言选择 system prompt
        system_prompt = SYSTEM_PROMPT_EN if language.lower() == "en" else SYSTEM_PROMPT_ZH

        raw_results = self.llm.chat_json(system_prompt, user_prompt)

        # V25.4 兼容：如果返回的是 dict，尝试提取其中的数组
        if isinstance(raw_results, dict):
            for key in ("evidence", "evidences", "results", "data", "items", "list"):
                if key in raw_results and isinstance(raw_results[key], list):
                    raw_results = raw_results[key]
                    break

        if not isinstance(raw_results, list):
            print(f"⚠️  段落 {para_id} 抽取结果不是数组，类型={type(raw_results).__name__}, 内容前200字={str(raw_results)[:200]}")
            return []

        cards: list[EvidenceCard] = []
        for i, item in enumerate(raw_results[:self.max_evidence_per_paragraph]):
            if not isinstance(item, dict):
                continue

            content = item.get("content", "").strip()
            if not content:
                continue

            evidence_type = self._parse_evidence_type(item.get("evidence_type", "fact"))

            safe_paper = self._sanitize_id(paper_id)
            safe_para = self._sanitize_id(para_id)

            card = EvidenceCard(
                evidence_id=f"ev_{safe_paper}_{safe_para}_{start_seq + i}",
                paper_id=paper_id,
                para_id=para_id,
                paper_title=para.get("paper_title", ""),
                section_l1=para.get("section_l1", ""),
                page=para.get("page", 0),
                evidence_type=evidence_type,
                content=content,
                original_quote=item.get("original_quote", "")[:500],
                model_system=item.get("model_system", ""),
                sample_size=item.get("sample_size", ""),
                treatment=item.get("treatment", ""),
                time_point=item.get("time_point", ""),
                mutation_type=item.get("mutation_type", "未知"),
                cell_type=item.get("cell_type", "未知"),
                measurement=item.get("measurement", "未知"),
                stimulus=item.get("stimulus", "未知"),
                confidence=item.get("confidence", 1.0),
            )

            # V25.2: 句内定位 + 置信度分层打标
            self._apply_location_and_confidence(card, text)

            cards.append(card)

        return cards

    def _build_user_prompt(self, text: str, topic: str, language: str = "en") -> str:
        """构建用户提示词。V25.9: 支持英文/中文。"""
        if language.lower() == "en":
            topic_hint = f"\nReview topic: {topic}\nPrioritize extracting evidence directly related to this topic." if topic else ""
            return f"Please extract evidence cards from the following paper paragraph:{topic_hint}\n\nParagraph content:\n{text[:3000]}"
        else:
            topic_hint = f"\n综述主题：{topic}\n请优先抽取与该主题直接相关的证据。" if topic else ""
            return f"请从以下论文段落中抽取证据卡片：{topic_hint}\n\n段落内容：\n{text[:3000]}"

    @staticmethod
    def _parse_evidence_type(raw: str) -> EvidenceType:
        """解析证据类型，容错处理。"""
        mapping = {
            "fact": EvidenceType.FACT,
            "mechanism": EvidenceType.MECHANISM,
            "claim": EvidenceType.CLAIM,
            "method": EvidenceType.METHOD,
            "limitation": EvidenceType.LIMITATION,
            "background": EvidenceType.BACKGROUND,
        }
        return mapping.get(str(raw).lower().strip(), EvidenceType.FACT)

    @staticmethod
    def _sanitize_id(raw: str, max_len: int = 24) -> str:
        """将 paper_id / para_id 中的空格和特殊字符替换为下划线，截断长度。
        避免 evidence_id 含空格导致 LLM 引用标记解析失败。"""
        import re
        cleaned = re.sub(r'[^\w\-]', '_', str(raw))
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        return cleaned[:max_len] if len(cleaned) > max_len else cleaned

    def _apply_location_and_confidence(self, card: EvidenceCard, paragraph_text: str) -> None:
        """V25.2: 对证据卡片做句内定位，并根据定位结果设置 confidence_level。

        规则：
        - 有 original_quote 且定位成功 → high
        - 有 original_quote 但定位失败 → medium
        - 没有 original_quote → low
        """
        from .models import ConfidenceLevel

        if card.original_quote and len(card.original_quote) >= 5:
            start, end = self._locator.locate(paragraph_text, card.original_quote)
            card.sentence_start = start
            card.sentence_end = end
            if start >= 0:
                card.confidence_level = ConfidenceLevel.HIGH
            else:
                card.confidence_level = ConfidenceLevel.MEDIUM
        else:
            card.confidence_level = ConfidenceLevel.LOW

    @staticmethod
    def _is_boilerplate(text: str) -> bool:
        """判断段落是否为 boilerplate（参考文献/版权/致谢等）。"""
        patterns = [
            r"^References?$",
            r"^Bibliography$",
            r"^Acknowledgements?$",
            r"^Copyright\s",
            r"©\s*\d{4}",
            r"^All rights reserved",
            r"^\[\d+\]\s",  # 参考文献条目
            r"^doi:\s*10\.",
        ]
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True
        return False


# ──────────────────────────────────────────────
# 自测（不依赖 LLM，测试数据结构和 boilerplate 过滤）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("🔍 Evidence Extractor Test (V25.0)")
    print("=" * 60)

    # 测试 boilerplate 过滤
    test_paras = [
        {"para_id": "p1", "paper_id": "paper1", "text": "STAT1 is a transcription factor that mediates interferon signaling. It is phosphorylated at Y701 by JAK kinases.", "section_l1": "Introduction", "page": 1},
        {"para_id": "p2", "paper_id": "paper1", "text": "References", "section_l1": "References", "page": 10},
        {"para_id": "p3", "paper_id": "paper1", "text": "[1] Smith J. et al. STAT1 and immunity. Cell 2020.", "section_l1": "References", "page": 10},
        {"para_id": "p4", "paper_id": "paper1", "text": "Short", "section_l1": "Methods", "page": 3},
    ]

    print("\n--- Boilerplate 过滤测试 ---")
    for p in test_paras:
        is_bp = EvidenceExtractor._is_boilerplate(p["text"])
        too_short = len(p["text"]) < 50
        status = "跳过(boilerplate)" if is_bp else ("跳过(太短)" if too_short else "✓ 处理")
        print(f"  {p['para_id']}: {status} — {p['text'][:50]}")

    print("\n--- 证据类型解析测试 ---")
    for t in ["fact", "MECHANISM", "claim", "unknown", "method"]:
        print(f"  '{t}' → {EvidenceExtractor._parse_evidence_type(t).value}")

    print("\n--- EvidenceCard 数据结构测试 ---")
    card = EvidenceCard(
        evidence_id="ev_paper1_p1_0",
        paper_id="paper1",
        para_id="p1",
        content="STAT1 mediates interferon signaling via Y701 phosphorylation.",
        original_quote="STAT1 is a transcription factor that mediates interferon signaling.",
        evidence_type=EvidenceType.MECHANISM,
    )
    print(f"  evidence_id: {card.evidence_id}")
    print(f"  source_label: {card.source_label()}")
    print(f"  evidence_type: {card.evidence_type.value}")
    print(f"  ✅ 数据结构正常")

    print("\n⚠️  实际 LLM 抽取测试需要 Ollama 服务运行。")
    print("    启动后运行: python -m services.review.llm_client 先验证 LLM 连接")
