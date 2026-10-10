"""
Sci-Pal 句子关系判定器 V33.5

用途：判定两个句子/证据之间的关系，用于 EvidenceCard 增量维护和去重。
5种关系类型：
1. duplicate（重复）：相似度 > 0.95，内容几乎完全相同
2. supplement（补充）：相似度 0.8-0.95 + 不同角度/侧重点
3. support（支持）：相似结论 + 独立来源（不同论文）
4. contradict（反驳）：结论相反/矛盾
5. update（更新）：新结论取代旧结论（时间更新/方法改进）

设计原则：
- 规则兜底：先用语义相似度做快速判定（重复/补充），开销低
- LLM 深度判定：对于支持/反驳/更新，需要理解语义，用 LLM 判定
- 置信度可解释：每种判定都有明确的置信度和判定依据
- 可配置：相似度阈值、是否启用 LLM 判定等都可配置
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime


# =============================================================================
# 关系类型定义
# =============================================================================

class SentenceRelationType(str, Enum):
    """句子关系类型"""
    DUPLICATE = "duplicate"        # 重复：内容几乎完全相同
    SUPPLEMENT = "supplement"      # 补充：相似但角度不同
    SUPPORT = "support"            # 支持：相似结论 + 独立来源
    CONTRADICT = "contradict"      # 反驳：结论相反/矛盾
    UPDATE = "update"              # 更新：新结论取代旧结论
    UNRELATED = "unrelated"        # 不相关：相似度很低
    UNKNOWN = "unknown"            # 未知：无法判定

    @property
    def label_zh(self) -> str:
        """中文标签"""
        return {
            "duplicate": "重复",
            "supplement": "补充",
            "support": "支持",
            "contradict": "反驳",
            "update": "更新",
            "unrelated": "不相关",
            "unknown": "未知",
        }[self.value]

    @property
    def color(self) -> str:
        """可视化颜色"""
        return {
            "duplicate": "#9CA3AF",   # 灰色
            "supplement": "#60A5FA",  # 蓝色
            "support": "#34D399",     # 绿色
            "contradict": "#F87171",  # 红色
            "update": "#FBBF24",      # 黄色
            "unrelated": "#E5E7EB",   # 浅灰
            "unknown": "#D1D5DB",     # 中灰
        }[self.value]


# =============================================================================
# 判定结果
# =============================================================================

@dataclass
class RelationJudgment:
    """关系判定结果"""
    relation: SentenceRelationType = SentenceRelationType.UNKNOWN
    confidence: float = 0.0  # 0-1，置信度
    method: str = ""  # 判定方法：rule / llm / hybrid
    reason: str = ""  # 判定依据（人类可读）
    similarity: float = 0.0  # 语义相似度（如果计算了的话）
    key_differences: list[str] = field(default_factory=list)  # 关键差异点
    key_similarities: list[str] = field(default_factory=list)  # 关键相似点

    def to_dict(self) -> dict:
        return {
            "relation": self.relation.value,
            "relation_label": self.relation.label_zh,
            "confidence": round(self.confidence, 4),
            "method": self.method,
            "reason": self.reason,
            "similarity": round(self.similarity, 4),
            "key_differences": self.key_differences,
            "key_similarities": self.key_similarities,
        }


# =============================================================================
# 句子关系判定器
# =============================================================================

class SentenceRelationClassifier:
    """
    句子关系判定器

    用法：
        classifier = SentenceRelationClassifier()
        result = classifier.classify(
            sentence1="STAT1 is activated by JAK phosphorylation",
            sentence2="JAK-mediated phosphorylation activates STAT1",
            paper_id1="paper_001",
            paper_id2="paper_002",
        )
        print(result.relation, result.confidence)
    """

    def __init__(
        self,
        llm_client=None,
        embedding_fn: Optional[Callable] = None,
        duplicate_threshold: float = 0.95,
        supplement_threshold: float = 0.80,
        unrelated_threshold: float = 0.30,
        use_llm: bool = True,
        llm_threshold: float = 0.60,  # 相似度高于此值才用 LLM 深度判定
    ):
        """
        Args:
            llm_client: LLM 客户端（用于深度判定，可选）
            embedding_fn: embedding 计算函数（输入文本，返回向量），可选
            duplicate_threshold: 重复判定阈值（相似度 > 此值判定为重复）
            supplement_threshold: 补充判定阈值（相似度在此值~duplicate之间判定为补充）
            unrelated_threshold: 不相关判定阈值（相似度 < 此值判定为不相关）
            use_llm: 是否启用 LLM 深度判定
            llm_threshold: 相似度高于此值才用 LLM 深度判定（避免对不相关的句子浪费 LLM 调用）
        """
        self.llm_client = llm_client
        self.embedding_fn = embedding_fn
        self.duplicate_threshold = duplicate_threshold
        self.supplement_threshold = supplement_threshold
        self.unrelated_threshold = unrelated_threshold
        self.use_llm = use_llm
        self.llm_threshold = llm_threshold

        # 矛盾关键词（用于规则判定反驳关系）
        self.contradiction_keywords = [
            ("increases", "decreases"),
            ("increase", "decrease"),
            ("promotes", "inhibits"),
            ("promote", "inhibit"),
            ("activates", "suppresses"),
            ("activate", "suppress"),
            ("upregulates", "downregulates"),
            ("upregulate", "downregulate"),
            ("enhances", "reduces"),
            ("enhance", "reduce"),
            ("positive", "negative"),
            ("higher", "lower"),
            ("more", "less"),
            ("gain", "loss"),
            ("gain-of-function", "loss-of-function"),
            ("GOF", "LOF"),
            ("overexpression", "knockdown"),
            ("wild-type", "mutant"),
            ("sensitive", "resistant"),
            ("beneficial", "detrimental"),
            ("protective", "pathogenic"),
        ]

    # -------------------------------------------------------------------------
    # 主判定接口
    # -------------------------------------------------------------------------

    def classify(
        self,
        sentence1: str,
        sentence2: str,
        paper_id1: str = "",
        paper_id2: str = "",
        date1: Optional[str] = None,
        date2: Optional[str] = None,
    ) -> RelationJudgment:
        """
        判定两个句子之间的关系

        Args:
            sentence1: 句子1（通常是已有句子/旧句子）
            sentence2: 句子2（通常是新句子/待判定句子）
            paper_id1: 句子1所属论文ID
            paper_id2: 句子2所属论文ID
            date1: 句子1所属论文发表日期（YYYY-MM-DD）
            date2: 句子2所属论文发表日期（YYYY-MM-DD）

        Returns:
            RelationJudgment 判定结果
        """
        result = RelationJudgment()

        # 步骤1：计算语义相似度（如果有 embedding 函数）
        similarity = self._compute_similarity(sentence1, sentence2)
        result.similarity = similarity

        # 步骤2：规则快速判定
        rule_result = self._rule_based_classify(
            sentence1, sentence2, similarity,
            paper_id1, paper_id2, date1, date2,
        )

        # 步骤3：决定是否需要 LLM 深度判定
        need_llm = (
            self.use_llm
            and self.llm_client is not None
            and similarity >= self.llm_threshold
            and rule_result.relation in [
                SentenceRelationType.SUPPLEMENT,
                SentenceRelationType.UNKNOWN,
            ]
        )

        if need_llm:
            llm_result = self._llm_based_classify(sentence1, sentence2, paper_id1, paper_id2)
            # 融合规则和 LLM 结果（LLM 置信度高时用 LLM，否则用规则）
            if llm_result.confidence > rule_result.confidence:
                result = llm_result
                result.method = "llm"
            else:
                result = rule_result
                result.method = "hybrid"
        else:
            result = rule_result
            result.method = "rule"

        result.similarity = similarity
        return result

    # -------------------------------------------------------------------------
    # 规则判定
    # -------------------------------------------------------------------------

    def _rule_based_classify(
        self,
        sentence1: str,
        sentence2: str,
        similarity: float,
        paper_id1: str,
        paper_id2: str,
        date1: Optional[str],
        date2: Optional[str],
    ) -> RelationJudgment:
        """基于规则的快速判定"""
        result = RelationJudgment(similarity=similarity, method="rule")

        # 1. 不相关：相似度很低
        if similarity < self.unrelated_threshold and similarity > 0:
            result.relation = SentenceRelationType.UNRELATED
            result.confidence = 0.9
            result.reason = f"语义相似度过低（{similarity:.2f} < {self.unrelated_threshold}）"
            return result

        # 2. 重复：相似度极高
        if similarity >= self.duplicate_threshold:
            result.relation = SentenceRelationType.DUPLICATE
            result.confidence = 0.95
            result.reason = f"语义相似度极高（{similarity:.2f} >= {self.duplicate_threshold}），内容几乎完全相同"
            return result

        # 3. 检查矛盾关键词
        if self._check_contradiction_keywords(sentence1, sentence2):
            result.relation = SentenceRelationType.CONTRADICT
            result.confidence = 0.7
            result.reason = "检测到矛盾关键词对（如 increase/decrease, promote/inhibit）"
            result.key_differences = self._extract_contradiction_pairs(sentence1, sentence2)
            return result

        # 4. 补充：相似度较高但未到重复程度
        if similarity >= self.supplement_threshold:
            # 检查是否来自不同论文（不同来源 → 支持；同一来源 → 补充）
            if paper_id1 and paper_id2 and paper_id1 != paper_id2:
                result.relation = SentenceRelationType.SUPPORT
                result.confidence = 0.6 + (similarity - self.supplement_threshold) * 2  # 0.6-0.9
                result.reason = f"相似度较高（{similarity:.2f}）且来自不同论文，结论相互支持"
            else:
                result.relation = SentenceRelationType.SUPPLEMENT
                result.confidence = 0.6 + (similarity - self.supplement_threshold) * 2
                result.reason = f"相似度较高（{similarity:.2f}）但未到重复程度，可能是不同角度的补充"
            return result

        # 5. 检查更新关系（时间更新 + 方法改进关键词）
        if self._check_update_relation(sentence1, sentence2, date1, date2):
            result.relation = SentenceRelationType.UPDATE
            result.confidence = 0.65
            result.reason = "检测到方法/技术更新关键词，且新论文时间更晚"
            return result

        # 6. 未知：无法通过规则判定
        result.relation = SentenceRelationType.UNKNOWN
        result.confidence = 0.3
        result.reason = "规则无法明确判定，建议使用 LLM 深度判定"
        return result

    # -------------------------------------------------------------------------
    # LLM 深度判定
    # -------------------------------------------------------------------------

    def _llm_based_classify(
        self,
        sentence1: str,
        sentence2: str,
        paper_id1: str = "",
        paper_id2: str = "",
    ) -> RelationJudgment:
        """基于 LLM 的深度判定"""
        result = RelationJudgment(method="llm")

        system_prompt = """你是一个科研文献句子关系判定专家。请判定两个句子之间的关系。

关系类型定义：
1. duplicate（重复）：两个句子表达几乎完全相同的意思，只是措辞不同
2. supplement（补充）：两个句子主题相似，但侧重点或角度不同，互为补充
3. support（支持）：两个句子来自不同论文，但结论一致，相互支持
4. contradict（反驳）：两个句子的结论相反或矛盾
5. update（更新）：句子2是对句子1的更新、改进或修正（如方法改进、结论修正）
6. unrelated（不相关）：两个句子主题完全不同

请严格按照以下 JSON 格式输出（不要输出其他内容）：
{
  "relation": "duplicate/supplement/support/contradict/update/unrelated",
  "confidence": 0.0-1.0,
  "reason": "判定依据（中文，简洁明了）",
  "key_similarities": ["相似点1", "相似点2"],
  "key_differences": ["差异点1", "差异点2"]
}"""

        user_prompt = f"""句子1（{paper_id1 or '未知来源'}）：
{sentence1}

句子2（{paper_id2 or '未知来源'}）：
{sentence2}

请判定这两个句子之间的关系。"""

        try:
            response = self.llm_client.chat(system_prompt, user_prompt)
            # 解析 JSON 响应
            import json
            # 尝试提取 JSON（LLM 可能输出 markdown 代码块）
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()

            data = json.loads(response)
            relation_str = data.get("relation", "unknown").lower()
            result.relation = SentenceRelationType(relation_str) if relation_str in [r.value for r in SentenceRelationType] else SentenceRelationType.UNKNOWN
            result.confidence = float(data.get("confidence", 0.5))
            result.reason = data.get("reason", "")
            result.key_similarities = data.get("key_similarities", [])
            result.key_differences = data.get("key_differences", [])
        except Exception as e:
            result.relation = SentenceRelationType.UNKNOWN
            result.confidence = 0.2
            result.reason = f"LLM 判定失败: {str(e)[:100]}"

        return result

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------

    def _compute_similarity(self, sentence1: str, sentence2: str) -> float:
        """计算两个句子的语义相似度"""
        if not self.embedding_fn:
            # 没有 embedding 函数时，用简单的词重叠度作为近似
            return self._word_overlap_similarity(sentence1, sentence2)

        try:
            vec1 = self.embedding_fn(sentence1)
            vec2 = self.embedding_fn(sentence2)
            # 余弦相似度
            dot = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(a * b for a, b in zip(vec1, vec2)) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)
        except Exception:
            return self._word_overlap_similarity(sentence1, sentence2)

    def _word_overlap_similarity(self, sentence1: str, sentence2: str) -> float:
        """基于词重叠度的简单相似度（Jaccard 相似度）"""
        # 简单分词（按空格和标点）
        def tokenize(text):
            text = text.lower()
            tokens = re.findall(r'[a-z0-9]+', text)
            # 去除停用词
            stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                        'would', 'could', 'should', 'may', 'might', 'must', 'can',
                        'of', 'in', 'to', 'for', 'with', 'on', 'at', 'by', 'from',
                        'as', 'into', 'through', 'during', 'before', 'after', 'above',
                        'below', 'between', 'and', 'but', 'or', 'nor', 'not', 'so',
                        'yet', 'both', 'either', 'neither', 'each', 'every', 'all',
                        'any', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
                        'only', 'own', 'same', 'than', 'too', 'very', 'just', 'because'}
            return set(t for t in tokens if t not in stopwords and len(t) > 2)

        set1 = tokenize(sentence1)
        set2 = tokenize(sentence2)

        if not set1 or not set2:
            return 0.0

        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union) if union else 0.0

    def _check_contradiction_keywords(self, sentence1: str, sentence2: str) -> bool:
        """检查是否包含矛盾关键词对"""
        s1_lower = sentence1.lower()
        s2_lower = sentence2.lower()

        for word1, word2 in self.contradiction_keywords:
            # 句子1包含 word1 且句子2包含 word2，或者反过来
            if (word1 in s1_lower and word2 in s2_lower) or \
               (word2 in s1_lower and word1 in s2_lower):
                return True
        return False

    def _extract_contradiction_pairs(self, sentence1: str, sentence2: str) -> list[str]:
        """提取矛盾关键词对"""
        pairs = []
        s1_lower = sentence1.lower()
        s2_lower = sentence2.lower()

        for word1, word2 in self.contradiction_keywords:
            if (word1 in s1_lower and word2 in s2_lower):
                pairs.append(f"句子1: {word1} ↔ 句子2: {word2}")
            elif (word2 in s1_lower and word1 in s2_lower):
                pairs.append(f"句子1: {word2} ↔ 句子2: {word1}")
        return pairs[:5]  # 最多返回 5 对

    def _check_update_relation(
        self,
        sentence1: str,
        sentence2: str,
        date1: Optional[str],
        date2: Optional[str],
    ) -> bool:
        """检查是否是更新关系"""
        update_keywords = [
            "improved", "improvement", "novel", "new method", "new approach",
            "updated", "revision", "revised", "corrected", "correction",
            "extended", "extension", "advanced", "state-of-the-art",
            "outperforms", "outperform", "better than", "superior to",
            "compared to previous", "compared with previous",
        ]

        s2_lower = sentence2.lower()
        has_update_keyword = any(kw in s2_lower for kw in update_keywords)

        # 检查时间：句子2比句子1新
        is_newer = False
        if date1 and date2:
            try:
                d1 = datetime.strptime(date1[:10], "%Y-%m-%d")
                d2 = datetime.strptime(date2[:10], "%Y-%m-%d")
                is_newer = d2 > d1
            except Exception:
                pass

        return has_update_keyword and (is_newer or not date1 or not date2)

    # -------------------------------------------------------------------------
    # 批量判定
    # -------------------------------------------------------------------------

    def classify_batch(
        self,
        pairs: list[tuple[str, str, dict]],
    ) -> list[RelationJudgment]:
        """
        批量判定多对句子的关系

        Args:
            pairs: 列表，每个元素是 (sentence1, sentence2, metadata_dict)
                  metadata_dict 可包含 paper_id1, paper_id2, date1, date2

        Returns:
            判定结果列表
        """
        results = []
        for sent1, sent2, meta in pairs:
            result = self.classify(
                sent1, sent2,
                paper_id1=meta.get("paper_id1", ""),
                paper_id2=meta.get("paper_id2", ""),
                date1=meta.get("date1"),
                date2=meta.get("date2"),
            )
            results.append(result)
        return results

    def find_relations_for_new_sentence(
        self,
        new_sentence: str,
        existing_sentences: list[dict],
        top_k: int = 5,
    ) -> list[tuple[dict, RelationJudgment]]:
        """
        为新句子查找与已有句子的关系（用于增量维护）

        Args:
            new_sentence: 新句子
            existing_sentences: 已有句子列表，每个 dict 包含 text, paper_id, date 等
            top_k: 返回最相关的前 K 个

        Returns:
            列表，每个元素是 (existing_sentence_dict, RelationJudgment)
        """
        results = []
        for existing in existing_sentences:
            result = self.classify(
                new_sentence,
                existing.get("text", ""),
                paper_id1="new",
                paper_id2=existing.get("paper_id", ""),
                date2=existing.get("date"),
            )
            if result.relation != SentenceRelationType.UNRELATED:
                results.append((existing, result))

        # 按相似度排序，取前 K 个
        results.sort(key=lambda x: x[1].similarity, reverse=True)
        return results[:top_k]


# =============================================================================
# 全局单例
# =============================================================================

_classifier_instance: Optional[SentenceRelationClassifier] = None


def get_relation_classifier(llm_client=None, embedding_fn=None) -> SentenceRelationClassifier:
    """获取全局句子关系判定器单例"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = SentenceRelationClassifier(
            llm_client=llm_client,
            embedding_fn=embedding_fn,
        )
    return _classifier_instance
