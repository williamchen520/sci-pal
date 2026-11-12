"""Pure SciFact chunk construction (no model / DB imports)."""

from __future__ import annotations

import re
from dataclasses import dataclass

WORD_RE = re.compile(r"\S+")


@dataclass
class Sentence:
    sentence_id: str
    paper_id: str
    ordinal: int
    text: str
    start: int
    end: int


@dataclass
class Unit:
    unit_id: str
    paper_id: str
    text: str
    anchors: tuple[str, ...]
    context: tuple[str, ...]


def context_window(
    paper_sentences: list[Sentence], start: int, end: int, radius: int = 1
) -> tuple[str, ...]:
    lo = max(0, start - radius)
    hi = min(len(paper_sentences), end + radius + 1)
    return tuple(sentence.sentence_id for sentence in paper_sentences[lo:hi])


def hard_chunks(paper_sentences: list[Sentence], words: int = 500) -> list[Unit]:
    text = " ".join(sentence.text for sentence in paper_sentences)
    matches = list(WORD_RE.finditer(text))
    units = []
    for index in range(0, len(matches), words):
        batch = matches[index : index + words]
        if not batch:
            continue
        start, end = batch[0].start(), batch[-1].end()
        anchors = [
            sentence.sentence_id
            for sentence in paper_sentences
            if sentence.end >= start and sentence.start <= end
        ]
        if not anchors:
            continue
        paper_id = paper_sentences[0].paper_id
        units.append(
            Unit(
                unit_id=f"{paper_id}:hard:{index // words:04d}",
                paper_id=paper_id,
                text=text[start:end],
                anchors=tuple(anchors),
                context=(),
            )
        )
    return units


def boundary_chunks(paper_sentences: list[Sentence], words: int = 500) -> list[Unit]:
    units = []
    current: list[Sentence] = []
    current_words = 0
    for sentence in paper_sentences:
        count = len(WORD_RE.findall(sentence.text))
        if current and current_words + count > words:
            units.append(
                Unit(
                    unit_id=f"{sentence.paper_id}:c{current[0].ordinal:04d}-{current[-1].ordinal:04d}",
                    paper_id=sentence.paper_id,
                    text=" ".join(item.text for item in current),
                    anchors=tuple(item.sentence_id for item in current),
                    context=context_window(
                        paper_sentences, current[0].ordinal, current[-1].ordinal
                    ),
                )
            )
            current = []
            current_words = 0
        current.append(sentence)
        current_words += count
    if current:
        units.append(
            Unit(
                unit_id=f"{current[0].paper_id}:c{current[0].ordinal:04d}-{current[-1].ordinal:04d}",
                paper_id=current[0].paper_id,
                text=" ".join(item.text for item in current),
                anchors=tuple(item.sentence_id for item in current),
                context=context_window(
                    paper_sentences, current[0].ordinal, current[-1].ordinal
                ),
            )
        )
    return units
