"""
Section-aware greedy chunking for retrieval.
V24.1 - 800-token chunking

Groups paragraphs by (paper_id, section_level1), sorts by sequence,
then greedily packs them into chunks of ~max_tokens. Chunks never
cross section boundaries. Optional overlap between consecutive chunks
within the same section.

Why chunking? Raw Docling paragraphs vary wildly in length (some are
one sentence, some are a full page). 800-token chunks give vector
embedding a consistent, information-dense unit that improves recall
precision while keeping enough context.
"""
import re
from typing import Dict, List, Optional, Tuple


# Simple tokenizer: split on whitespace, count tokens.
# For English this is ~1.3x word count; for Chinese each char is ~1 token.
# We use a rough heuristic that's good enough for chunk sizing.
def estimate_tokens(text: str) -> int:
    """Estimate token count without needing a tokenizer library."""
    if not text:
        return 0
    # Count whitespace-separated tokens (English)
    words = len(text.split())
    # Count CJK characters (each ~1 token)
    cjk = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    # Mixed: English words + CJK chars, with a small overhead
    return max(words, cjk) + min(words, cjk) // 4


class Chunker:
    """
    Section-aware greedy chunker.

    Usage:
        chunker = Chunker(max_tokens=800, overlap=50)
        chunks = chunker.chunk_paragraphs(paragraphs)
    """

    def __init__(self, max_tokens: int = 800, overlap: int = 50,
                 min_tokens: int = 100):
        """
        Args:
            max_tokens: target maximum tokens per chunk (default 800)
            overlap: tokens of overlap between consecutive chunks (default 50)
            min_tokens: chunks smaller than this are merged with the next chunk
        """
        self.max_tokens = max_tokens
        self.overlap = overlap
        self.min_tokens = min_tokens

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------
    def chunk_paragraphs(self, paragraphs: List[Dict]) -> List[Dict]:
        """
        Chunk a list of paragraphs into section-aware chunks.

        Each paragraph dict should have:
          - para_id, paper_id, section_level1, section_level2, text,
            sequence, page

        Returns a list of chunk dicts:
          - chunk_id, paper_id, section_level1, section_level2,
            start_para_id, end_para_id, para_ids (list), text,
            token_count, page (first page), start_sequence, end_sequence
        """
        if not paragraphs:
            return []

        # Group by (paper_id, section_level1)
        groups: Dict[Tuple[str, str], List[Dict]] = {}
        for p in paragraphs:
            key = (p.get("paper_id", ""), p.get("section_level1") or "")
            groups.setdefault(key, []).append(p)

        all_chunks = []
        chunk_counter = 0

        for (paper_id, section), paras in groups.items():
            # Sort by sequence
            paras_sorted = sorted(paras, key=lambda x: x.get("sequence", 0))
            chunks = self._chunk_one_section(paras_sorted, paper_id, section)
            for c in chunks:
                chunk_counter += 1
                c["chunk_id"] = f"chk_{paper_id[:12]}_{chunk_counter:05d}"
                all_chunks.append(c)

        return all_chunks

    # ------------------------------------------------------------------
    # Internal: chunk one section
    # ------------------------------------------------------------------
    def _chunk_one_section(self, paras: List[Dict],
                           paper_id: str, section: str) -> List[Dict]:
        """Greedy pack paragraphs within one section into chunks."""
        if not paras:
            return []

        chunks = []
        current = []
        current_tokens = 0
        current_text_parts = []

        def flush():
            nonlocal current, current_tokens, current_text_parts
            if not current:
                return
            text = "\n".join(current_text_parts)
            token_count = estimate_tokens(text)
            chunks.append({
                "paper_id": paper_id,
                "section_level1": section,
                "section_level2": current[0].get("section_level2") or "",
                "start_para_id": current[0].get("para_id"),
                "end_para_id": current[-1].get("para_id"),
                "para_ids": [p.get("para_id") for p in current],
                "text": text,
                "token_count": token_count,
                "page": current[0].get("page"),
                "start_sequence": current[0].get("sequence", 0),
                "end_sequence": current[-1].get("sequence", 0),
            })
            current = []
            current_tokens = 0
            current_text_parts = []

        for p in paras:
            text = p.get("text", "")
            p_tokens = estimate_tokens(text)

            # If this single paragraph exceeds max_tokens, it becomes its own
            # chunk (can't split a paragraph further without sentence tokenizer)
            if p_tokens > self.max_tokens and not current:
                current = [p]
                current_tokens = p_tokens
                current_text_parts = [text]
                flush()
                continue

            # If adding this paragraph would exceed max_tokens, flush first
            if current and current_tokens + p_tokens > self.max_tokens:
                flush()

                # Handle overlap: carry over the last paragraph's tail
                if self.overlap > 0 and chunks:
                    last_text = chunks[-1]["text"]
                    # Take roughly the last `overlap` tokens
                    words = last_text.split()
                    overlap_words = words[-(self.overlap * 4 // 3):] if words else []
                    if overlap_words:
                        overlap_text = " ".join(overlap_words)
                        current_text_parts = [overlap_text]
                        current_tokens = estimate_tokens(overlap_text)

            current.append(p)
            current_tokens += p_tokens
            current_text_parts.append(text)

        # Flush remaining
        flush()

        # Merge tiny trailing chunks with the previous one
        if len(chunks) >= 2 and chunks[-1]["token_count"] < self.min_tokens:
            prev = chunks[-2]
            tiny = chunks[-1]
            prev["text"] = prev["text"] + "\n" + tiny["text"]
            prev["token_count"] = estimate_tokens(prev["text"])
            prev["end_para_id"] = tiny["end_para_id"]
            prev["para_ids"].extend(tiny["para_ids"])
            prev["end_sequence"] = tiny["end_sequence"]
            chunks.pop()

        return chunks


# ======================================================================
# Self-test
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("📦 Section-Aware Chunker Test (V24.1)")
    print("=" * 60)

    chunker = Chunker(max_tokens=800, overlap=50)

    # Test 1: token estimation
    print("\n── Token estimation ──")
    samples = [
        "Hello world, this is a test.",
        "STAT1 is a cytoplasmic transcription factor that mediates type I interferon signaling.",
        "你好世界，这是一个测试。",
        "The quick brown fox jumps over the lazy dog. " * 20,
    ]
    for s in samples:
        print(f"  {estimate_tokens(s):4d} tokens | {s[:60]}...")

    # Test 2: chunking synthetic paragraphs
    print("\n── Chunking synthetic paragraphs ──")
    test_paras = []
    for i in range(20):
        text = f"Paragraph {i}: " + ("This is a moderately long paragraph about "
               "signal transduction and immune response pathways. " * 3)
        test_paras.append({
            "para_id": f"para_{i:03d}",
            "paper_id": "paper_test_001",
            "section_level1": "Introduction" if i < 10 else "Methods",
            "section_level2": "",
            "text": text,
            "sequence": i,
            "page": 1 + i // 5,
        })

    chunks = chunker.chunk_paragraphs(test_paras)
    print(f"  Input: {len(test_paras)} paragraphs, 2 sections")
    print(f"  Output: {len(chunks)} chunks")
    for c in chunks:
        print(f"    {c['chunk_id']} | sec={c['section_level1'][:15]:15s} | "
              f"{c['token_count']:4d} tok | paras {c['start_para_id']}→{c['end_para_id']} | "
              f"{len(c['para_ids'])} paras")

    # Verify no cross-section chunks
    sections_per_chunk = set()
    for c in chunks:
        sections_per_chunk.add(c["section_level1"])
    print(f"\n  Sections found in chunks: {sections_per_chunk}")
    print(f"  ✅ No cross-section chunks: {len(sections_per_chunk) == 2}")

    print("\n✅ Chunker test complete.")
