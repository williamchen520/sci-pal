"""
V25.0 - Pydantic 数据模型：综述生成智能体的核心数据结构。

所有模型强制绑定文献来源（paper_id / para_id），这是防幻觉的基础。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 证据卡片（EvidenceCard）—— 综述的最小可信单元
# ──────────────────────────────────────────────

class EvidenceType(str, Enum):
    """证据类型，用于区分陈述性质。"""
    FACT = "fact"                    # 已证实的实验事实/数据
    MECHANISM = "mechanism"          # 分子机制/通路解释
    CLAIM = "claim"                  # 作者的论断/观点
    METHOD = "method"                # 实验方法/条件
    LIMITATION = "limitation"        # 研究局限性
    BACKGROUND = "background"        # 背景知识/引言


class ConfidenceLevel(str, Enum):
    """V25.2: 置信度分层——风控基础字段。
    high: 有原文引用且能在段落中精确定位，内容完整
    medium: 有内容但原文引用不完整，或定位有偏差
    low: 只有简短描述，无原文引用，或定位失败
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceCard(BaseModel):
    """
    结构化证据卡片——从单篇文献的单个段落中抽取的一条证据。
    每条证据强制绑定 paper_id + para_id，可反向溯源到 PDF 原文。
    """
    evidence_id: str = Field(..., description="证据唯一ID，格式 ev_{paper_id}_{para_id}_{seq}")
    paper_id: str = Field(..., description="来源论文ID")
    para_id: str = Field(..., description="来源段落ID（强制绑定，防幻觉核心）")
    paper_title: str = Field("", description="来源论文标题（冗余存储，方便渲染）")
    section_l1: str = Field("", description="来源章节（一级）")
    page: int = Field(0, description="来源页码")

    evidence_type: EvidenceType = Field(EvidenceType.FACT, description="证据类型")
    content: str = Field(..., description="证据内容（从原文抽取/改写的核心陈述）")
    original_quote: str = Field("", description="原文引用（精确到句，用于校验）")

    # 实验条件元数据（用于冲突检测时对比条件差异）
    model_system: str = Field("", description="实验模型（如 小鼠/细胞系/患者样本）")
    sample_size: str = Field("", description="样本量")
    treatment: str = Field("", description="处理/干预条件")
    time_point: str = Field("", description="时间点")

    # V25.5: 细粒度条件标签（用于冲突检测前的条件可比性检查，减少伪争议）
    mutation_type: str = Field("", description="突变类型：GOF(功能获得)/LOF(功能丧失)/特定位点突变/未知/不适用")
    cell_type: str = Field("", description="细胞类型：如 单核细胞/T细胞/成纤维细胞/细胞系名称/未知")
    measurement: str = Field("", description="测量指标：mRNA/总蛋白/磷酸化蛋白/功能活性/临床表型/未知")
    stimulus: str = Field("", description="刺激条件：IFN-α/IFN-gamma/IL-27/未刺激/未知")

    # 置信度与状态
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="LLM 抽取置信度")
    confidence_level: ConfidenceLevel = Field(ConfidenceLevel.MEDIUM, description="V25.2: 置信度分层（风控基础）")
    verified: bool = Field(False, description="是否经过引用校验Agent验证")

    # V33.4: 证据来源与匹配元数据（用于去重和综合置信度计算）
    source_type: str = Field("full_text", description="来源类型：full_text（全文段落）/ abstract（摘要）")
    match_method: str = Field("hybrid", description="匹配方式：vector（向量检索）/ bm25（全文检索）/ entity（实体匹配）/ hybrid（混合检索）")
    rerank_score: float = Field(0.0, ge=0.0, le=1.0, description="重排分数（bge-reranker-base 输出，0-1）")
    dedupe_key: str = Field("", description="去重 key（paper_id + para_id 的哈希，用于精确去重）")
    retrieval_rank: int = Field(0, description="检索排名（在召回结果中的位置，0 表示未参与排序）")

    # V25.2: 句内定位——original_quote 在段落中的字符偏移
    sentence_start: int = Field(-1, description="原文引用在段落中的起始字符偏移（-1表示未定位）")
    sentence_end: int = Field(-1, description="原文引用在段落中的结束字符偏移（-1表示未定位）")

    def source_label(self) -> str:
        """返回简短来源标签，用于综述引用标记。"""
        return f"[{self.paper_id}:{self.para_id}]"

    def compute_quality_score(self) -> float:
        """V33.4: 计算证据综合质量分（0-1），用于生成时按质量排序和低质量过滤。

        计算公式：
        quality = 0.4 × source_type_weight + 0.3 × match_method_weight + 0.3 × rerank_score

        来源类型权重：
        - full_text: 1.0（全文段落，最可靠）
        - abstract: 0.6（摘要，信息有限）

        匹配方式权重：
        - hybrid: 1.0（混合检索，最全面）
        - vector: 0.8（向量检索，语义匹配）
        - bm25: 0.7（全文检索，关键词匹配）
        - entity: 0.6（实体匹配，精确但可能遗漏）
        """
        source_weights = {
            "full_text": 1.0,
            "abstract": 0.6,
        }
        match_weights = {
            "hybrid": 1.0,
            "vector": 0.8,
            "bm25": 0.7,
            "entity": 0.6,
        }

        source_w = source_weights.get(self.source_type, 0.5)
        match_w = match_weights.get(self.match_method, 0.5)
        rerank_w = min(max(self.rerank_score, 0.0), 1.0)

        quality = 0.4 * source_w + 0.3 * match_w + 0.3 * rerank_w
        return round(quality, 4)


# ──────────────────────────────────────────────
# 综述大纲（ReviewOutline）
# ──────────────────────────────────────────────

class ReviewParagraph(BaseModel):
    """综述大纲中的一个段落（V25.8: 段落级自定义大纲）。"""
    paragraph_id: str = Field(..., description="段落ID，如 sec_01_para_01")
    topic: str = Field(..., description="段落主题（用户可自定义，比如'功能缺失性突变'）")
    description: str = Field("", description="段落详细描述/写作要点（可选）")
    order: int = Field(0, description="段落在章节内的顺序")
    assigned_paper_ids: list[str] = Field(default_factory=list, description="分配给本段的论文ID列表（用户可指定）")
    assigned_evidence_ids: list[str] = Field(default_factory=list, description="分配给本段的证据ID列表（可选，更细粒度）")


class ReviewSection(BaseModel):
    """综述大纲中的一个章节。"""
    section_id: str = Field(..., description="章节ID，如 sec_01")
    title: str = Field(..., description="章节标题")
    description: str = Field("", description="章节内容描述/写作要点")
    order: int = Field(0, description="章节顺序")
    assigned_paper_ids: list[str] = Field(default_factory=list, description="分配给本章的论文ID列表")
    assigned_evidence_ids: list[str] = Field(default_factory=list, description="分配给本章的证据ID列表")
    # V25.8: 段落级大纲（每章分2-3段，每段有明确主题；用户可自定义段落主题和论文分配）
    paragraphs: list[ReviewParagraph] = Field(default_factory=list, description="章节内的段落列表（段落级大纲）")


class ReviewOutline(BaseModel):
    """综述大纲——由规划Agent生成，指导撰写Agent逐章写作。"""
    topic: str = Field(..., description="综述主题")
    sections: list[ReviewSection] = Field(default_factory=list, description="章节列表（按顺序）")
    total_papers: int = Field(0, description="涉及的论文总数")
    total_evidence: int = Field(0, description="涉及的证据卡片总数")

    def get_section(self, section_id: str) -> Optional[ReviewSection]:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None


# ──────────────────────────────────────────────
# 综述句子（ReviewSentence）—— 撰写与校验的最小单元
# ──────────────────────────────────────────────

class SentenceStatus(str, Enum):
    """句子状态，由引用校验Agent设置。"""
    VERIFIED = "verified"          # 已验证：有对应证据卡片
    UNVERIFIED = "unverified"      # 未验证：暂未找到证据（警告）
    REJECTED = "rejected"          # 已拒绝：无证据支撑，从正文剔除
    CONTROVERSIAL = "controversial"  # 有争议：多篇文献结论不一致


class ReviewSentence(BaseModel):
    """
    综述中的单个句子。撰写Agent生成，校验Agent逐句审核。
    每个句子必须关联至少一个 evidence_id，否则会被标记为 REJECTED。
    """
    sentence_id: str = Field(..., description="句子ID，格式 sent_{sec}_{seq}")
    section_id: str = Field(..., description="所属章节ID")
    text: str = Field(..., description="句子文本")
    evidence_ids: list[str] = Field(default_factory=list, description="支撑本句的证据ID列表（强制非空才能通过校验）")
    status: SentenceStatus = Field(SentenceStatus.UNVERIFIED, description="校验状态")
    verification_note: str = Field("", description="校验备注（如被拒绝的原因）")

    def citation_markers(self) -> str:
        """返回引用标记字符串，如 [paper1:para1][paper2:para2]。"""
        if not self.evidence_ids:
            return ""
        return "".join(f"[{eid}]" for eid in self.evidence_ids)


# ──────────────────────────────────────────────
# 综述初稿（ReviewDraft）
# ──────────────────────────────────────────────

class ReviewDraft(BaseModel):
    """综述初稿——撰写Agent的输出，校验Agent的输入。"""
    topic: str = Field(..., description="综述主题")
    outline: ReviewOutline = Field(..., description="对应的大纲")
    sentences: list[ReviewSentence] = Field(default_factory=list, description="所有句子（按章节顺序）")
    evidence_cards: dict[str, EvidenceCard] = Field(default_factory=dict, description="证据卡片字典 {evidence_id: card}")

    def sentences_by_section(self, section_id: str) -> list[ReviewSentence]:
        return [s for s in self.sentences if s.section_id == section_id]

    def verified_sentences(self) -> list[ReviewSentence]:
        return [s for s in self.sentences if s.status == SentenceStatus.VERIFIED]

    def rejected_sentences(self) -> list[ReviewSentence]:
        return [s for s in self.sentences if s.status == SentenceStatus.REJECTED]

    def stats(self) -> dict:
        return {
            "total_sentences": len(self.sentences),
            "verified": len(self.verified_sentences()),
            "rejected": len(self.rejected_sentences()),
            "unverified": len([s for s in self.sentences if s.status == SentenceStatus.UNVERIFIED]),
            "controversial": len([s for s in self.sentences if s.status == SentenceStatus.CONTROVERSIAL]),
            "total_evidence": len(self.evidence_cards),
            "pass_rate": round(len(self.verified_sentences()) / max(len(self.sentences), 1), 3),
        }


# ──────────────────────────────────────────────
# V25.3: 证据间关系（Relation）—— 关系图谱的边
# ──────────────────────────────────────────────

class RelationType(str, Enum):
    """证据卡片之间的逻辑关系类型。"""
    SUPPORTS = "supports"        # 支持：一条证据的结论被另一条证据佐证
    CONTRADICTS = "contradicts"  # 矛盾：两条证据结论不一致（冲突识别的核心输入）
    ELABORATES = "elaborates"    # 展开：一条证据对另一条做更详细的解释/补充
    UNRELATED = "unrelated"      # 无关：两条证据没有直接逻辑关系


class EvidenceRelation(BaseModel):
    """
    两条证据卡片之间的逻辑关系。
    由 RelationExtractor 用 LLM 判定，是冲突识别和综述"争议章节"的基础。
    """
    relation_id: str = Field(..., description="关系唯一ID，格式 rel_{src}_{tgt}")
    source_evidence_id: str = Field(..., description="源证据ID")
    target_evidence_id: str = Field(..., description="目标证据ID")
    relation_type: RelationType = Field(RelationType.UNRELATED, description="关系类型")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="LLM 判定置信度")
    explanation: str = Field("", description="LLM 对判定理由的简短解释")
    condition_diff: str = Field("", description="实验条件差异分析（contradicts 时必填，用于解释为什么结论不同）")

    # V25.5: 条件差异标记——区分"真正矛盾"和"条件不同导致的不同结果"
    condition_mismatch: bool = Field(False, description="是否为条件差异型（结论相反但实验条件明显不同，非真矛盾）")
    mismatch_reason: str = Field("", description="条件差异的具体原因（如：突变类型不同GOF vs LOF、测量指标不同mRNA vs 蛋白等）")


# ──────────────────────────────────────────────
# V25.3: 冲突点（Conflict）—— 多篇文献结论不一致的汇总
# ──────────────────────────────────────────────

class Conflict(BaseModel):
    """
    一个争议点：多条证据结论不一致，汇总为一个可写入综述"研究争议"章节的条目。
    由 ConflictDetector 基于 contradicts 关系自动汇总生成。
    """
    conflict_id: str = Field(..., description="冲突唯一ID，格式 conflict_{seq}")
    topic: str = Field(..., description="争议点主题（一句话概括在争论什么）")
    evidence_ids: list[str] = Field(default_factory=list, description="涉及的证据ID列表")
    paper_ids: list[str] = Field(default_factory=list, description="涉及的论文ID列表")
    summary: str = Field("", description="争议小结（可直接写入综述的段落文本）")
    condition_analysis: str = Field("", description="实验条件差异分析（样本/模型/时间点/处理方式的不同如何导致结论差异）")
    sides: list[dict] = Field(default_factory=list, description="争议各方观点 [{side: '正方', evidence_ids: [...], claim: '...'}]")

    # V25.5: 冲突类型——区分"真正矛盾"和"条件差异导致的不同结果"
    conflict_type: str = Field("true_controversy", description="冲突类型：true_controversy（真正矛盾，条件可比）/ condition_difference（条件差异型，结论不同但实验条件明显不同）")


# ──────────────────────────────────────────────
# 最终输出（ReviewOutput）
# ──────────────────────────────────────────────

class ReviewOutput(BaseModel):
    """最终综述输出——校验通过后的 Markdown 文本 + 元数据。"""
    topic: str = Field(..., description="综述主题")
    markdown: str = Field(..., description="综述 Markdown 全文（仅含已验证句子）")
    references: list[dict] = Field(default_factory=list, description="参考文献列表 [{paper_id, title, authors, journal, year}]")
    stats: dict = Field(default_factory=dict, description="统计信息（句子数/通过率/证据数）")
    warnings: list[str] = Field(default_factory=list, description="警告信息（被拒绝的句子、有争议的点等）")
    # V25.3: 关系图谱与冲突识别结果
    relations: list[dict] = Field(default_factory=list, description="证据间关系列表（supports/contradicts/elaborates）")
    conflicts: list[dict] = Field(default_factory=list, description="识别到的争议点列表（含实验条件差异分析）")
    # V25.7: 综述模板类型
    review_type: str = Field(default="narrative", description="综述模板类型（narrative/comparative/systematic）")
