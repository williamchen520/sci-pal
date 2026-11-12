"""Heading-aware Markdown chunking for the independent docs RAG database.

No 500-word hard cut: split at headings and paragraph boundaries first, then
fall back to sentence/character windows with overlap only for oversized blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
SENTENCE_RE = re.compile(r"(?<=[。！？.!?])\s+")
WORD_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading: str
    text: str
    token_count: int


def token_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def _sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            sections.append((" > ".join(stack), text))
        body.clear()

    for line in markdown.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            body.append(line)
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            stack = stack[: level - 1]
            stack.append(match.group(2).strip())
        else:
            body.append(line)
    flush()
    return sections


def _split_oversized(text: str, max_chars: int, overlap: int) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    result: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                result.append(current)
                current = ""
            sentences = [s.strip() for s in SENTENCE_RE.split(part) if s.strip()]
            if len(sentences) <= 1:
                step = max(max_chars - overlap, 1)
                for start in range(0, len(part), step):
                    result.append(part[start : start + max_chars])
                continue
            buf = ""
            for sentence in sentences:
                if len(buf) + len(sentence) + 1 > max_chars and buf:
                    result.append(buf)
                    buf = buf[-overlap:] if overlap else ""
                buf = (buf + " " + sentence).strip()
            if buf:
                result.append(buf)
        elif len(current) + len(part) + 2 > max_chars and current:
            result.append(current)
            current = part
        else:
            current = (current + "\n\n" + part).strip()
    if current:
        result.append(current)
    return result


def chunk_markdown(
    markdown: str,
    *,
    max_chars: int = 1600,
    overlap: int = 200,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, section in _sections(markdown):
        pieces = (
            [section]
            if len(section) <= max_chars
            else _split_oversized(section, max_chars, overlap)
        )
        for piece in pieces:
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    heading=heading,
                    text=piece,
                    token_count=token_count(piece),
                )
            )
    return chunks
