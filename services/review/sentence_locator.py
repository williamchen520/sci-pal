"""
V25.2 - 句内定位模块（SentenceLocator）。

将 LLM 抽取的 original_quote 在段落全文中精确定位，返回字符偏移。
用于综述句子点击溯源时高亮原文中的具体句子，而不是整段。

定位策略（从精确到模糊）：
1. 精确匹配：quote 直接出现在 paragraph 中
2. 规范化匹配：去除多余空白后匹配
3. 模糊匹配：difflib 找最相似的子串（相似度 >= 0.6）
4. 定位失败：返回 (-1, -1)

用法:
    locator = SentenceLocator()
    start, end = locator.locate(paragraph_text, original_quote)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


class SentenceLocator:
    """句内定位器：将原文引用映射到段落中的字符偏移。"""

    def __init__(self, min_similarity: float = 0.6):
        """
        Args:
            min_similarity: 模糊匹配的最低相似度阈值，低于此值视为定位失败
        """
        self.min_similarity = min_similarity

    def locate(self, paragraph: str, quote: str) -> tuple[int, int]:
        """
        在段落中定位 quote 的起始和结束字符偏移。

        Args:
            paragraph: 段落全文
            quote: LLM 抽取的原文引用（可能不完全精确）

        Returns:
            (start, end) 字符偏移；定位失败返回 (-1, -1)
        """
        if not paragraph or not quote:
            return -1, -1

        quote = quote.strip()
        if len(quote) < 5:
            return -1, -1

        # 策略1: 精确匹配
        idx = paragraph.find(quote)
        if idx >= 0:
            return idx, idx + len(quote)

        # 策略2: 规范化匹配（去除多余空白）
        norm_para = self._normalize(paragraph)
        norm_quote = self._normalize(quote)
        idx = norm_para.find(norm_quote)
        if idx >= 0:
            # 将规范化后的偏移映射回原文偏移
            real_start = self._map_norm_offset_to_original(paragraph, norm_para, idx)
            real_end = self._map_norm_offset_to_original(paragraph, norm_para, idx + len(norm_quote))
            return real_start, real_end

        # 策略3: 模糊匹配（滑动窗口 + SequenceMatcher）
        result = self._fuzzy_match(paragraph, quote)
        if result:
            return result

        return -1, -1

    def locate_batch(self, paragraph: str, quotes: list[str]) -> list[tuple[int, int]]:
        """批量定位多个 quote。"""
        return [self.locate(paragraph, q) for q in quotes]

    # ──────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """规范化文本：多个空白合并为一个，去除首尾空白。"""
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _map_norm_offset_to_original(original: str, normalized: str, norm_offset: int) -> int:
        """
        将规范化文本中的字符偏移映射回原文偏移。
        规范化只做了空白合并，所以逐个字符比对即可。
        """
        norm_idx = 0
        for orig_idx, ch in enumerate(original):
            if norm_idx >= norm_offset:
                return orig_idx
            if ch.isspace():
                # 原文中的连续空白在规范化中是一个空格
                # 跳过原文中连续的空白
                continue
            norm_idx += 1
            # 跳过规范化中对应的空格
            if norm_idx < len(normalized) and normalized[norm_idx] == ' ':
                norm_idx += 1
        return len(original)

    def _fuzzy_match(self, paragraph: str, quote: str) -> tuple[int, int] | None:
        """
        模糊匹配：在段落中滑动与 quote 等长的窗口，找相似度最高的位置。
        为了性能，窗口长度在 quote 长度的 0.5~2.0 倍范围内扫描。
        """
        quote_len = len(quote)
        para_len = len(paragraph)

        if para_len < quote_len // 2:
            return None

        best_ratio = 0.0
        best_start = -1
        best_end = -1

        # 尝试不同的窗口长度
        for window_len in (quote_len, int(quote_len * 0.8), int(quote_len * 1.2), int(quote_len * 1.5)):
            if window_len < 5 or window_len > para_len:
                continue

            step = max(1, window_len // 4)  # 步长为窗口的1/4，平衡精度和性能
            for start in range(0, para_len - window_len + 1, step):
                window = paragraph[start:start + window_len]
                ratio = SequenceMatcher(None, quote, window).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_start = start
                    best_end = start + window_len

        if best_ratio >= self.min_similarity and best_start >= 0:
            return best_start, best_end
        return None


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("📍 Sentence Locator Test (V25.2)")
    print("=" * 60)

    locator = SentenceLocator()

    paragraph = (
        "STAT1 is a cytoplasmic transcription factor that mediates type I, "
        "type II, and type III interferon signaling. When ligands bind to the "
        "receptor, JAKs are activated and phosphorylate tyrosine residues. "
        "STAT1 is then recruited and phosphorylated at tyrosine 701 (Y701)."
    )

    test_cases = [
        ("精确匹配", "STAT1 is then recruited and phosphorylated at tyrosine 701 (Y701)."),
        ("含多余空白", "STAT1   is   a   cytoplasmic   transcription   factor"),
        ("子串匹配", "phosphorylate tyrosine residues"),
        ("轻微差异", "JAKs are activated and phosphorylate tyrosine"),  # 少了 residues
        ("完全不相关", "This sentence does not appear in the paragraph at all."),
        ("太短", "STAT1"),
    ]

    for name, quote in test_cases:
        start, end = locator.locate(paragraph, quote)
        if start >= 0:
            matched = paragraph[start:end]
            print(f"  ✅ [{name}] ({start}, {end}) → {matched[:50]}...")
        else:
            print(f"  ❌ [{name}] 定位失败（符合预期）" if "不相关" in name or "太短" in name else f"  ⚠️  [{name}] 定位失败")

    print("\n✅ 句内定位测试完成。")
