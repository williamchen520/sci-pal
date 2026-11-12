"""Loaders for public evaluation sets used by experiment harnesses.

SciFact (BEIR layout) and QASPER have different evidence granularity. Keep the
difference explicit instead of pretending both are sentence-level:

* SciFact qrels are document-level; text is split into sentences for retrieval.
* QASPER answers carry paragraph/free-text evidence; sentence ids are generated
  for retrieval and context, not for gold sentence Recall.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


@dataclass(frozen=True)
class PublicPaper:
    paper_id: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicSentence:
    sentence_id: str
    paper_id: str
    ordinal: int
    text: str


@dataclass(frozen=True)
class PublicClaim:
    claim_id: str
    text: str
    gold_paper_ids: tuple[str, ...] = ()
    gold_sentence_ids: tuple[str, ...] = ()
    evidence_level: str = "document"
    label: str | None = None


@dataclass
class PublicDataset:
    name: str
    papers: list[PublicPaper]
    sentences: list[PublicSentence]
    claims: list[PublicClaim]
    evidence_level: str
    source: str

    def paper(self, paper_id: str) -> PublicPaper | None:
        return next((paper for paper in self.papers if paper.paper_id == paper_id), None)


def split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]


def _sentence_rows(paper_id: str, text: str) -> list[PublicSentence]:
    return [
        PublicSentence(
            sentence_id=f"{paper_id}_s{index:04d}",
            paper_id=paper_id,
            ordinal=index,
            text=sentence,
        )
        for index, sentence in enumerate(split_sentences(text))
    ]


def load_scifact(
    corpus_path: str | Path,
    queries_path: str | Path,
    qrels_path: str | Path,
) -> PublicDataset:
    """Load BEIR-layout SciFact.

    ``qrels`` are query -> document relevance, not sentence evidence. The
    returned claims use ``evidence_level='document'``.
    """
    corpus_path = Path(corpus_path)
    queries_path = Path(queries_path)
    qrels_path = Path(qrels_path)

    papers: list[PublicPaper] = []
    sentences: list[PublicSentence] = []
    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        doc_id = str(item.get("_id") or item.get("doc_id") or item.get("id"))
        text = str(item.get("text") or item.get("abstract") or "")
        papers.append(
            PublicPaper(
                paper_id=f"scifact_{doc_id}",
                title=str(item.get("title") or ""),
                text=text,
                metadata=item.get("metadata") or {},
            )
        )
        sentences.extend(_sentence_rows(f"scifact_{doc_id}", text))

    queries: dict[str, str] = {}
    for line in queries_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        queries[str(item.get("_id") or item.get("id"))] = str(item.get("text") or "")

    gold: dict[str, list[str]] = {}
    for line in qrels_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lower().startswith("query"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        query_id, doc_id, score = parts[0], parts[1], parts[2]
        if int(float(score)) > 0:
            gold.setdefault(query_id, []).append(f"scifact_{doc_id}")

    claims = [
        PublicClaim(
            claim_id=query_id,
            text=text,
            gold_paper_ids=tuple(gold.get(query_id, [])),
            evidence_level="document",
        )
        for query_id, text in queries.items()
    ]
    return PublicDataset(
        name="scifact",
        papers=papers,
        sentences=sentences,
        claims=claims,
        evidence_level="document",
        source=str(corpus_path.parent),
    )


def load_qasper(path: str | Path, *, limit: int | None = None) -> PublicDataset:
    """Load QASPER v0.3.

    QASPER evidence is free text/paragraph-level. ``gold_sentence_ids`` stays
    empty; use ``evidence_level='paragraph'`` rather than claiming sentence
    Recall.
    """
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs = list(data.items()) if isinstance(data, dict) else list(enumerate(data))

    papers: list[PublicPaper] = []
    sentences: list[PublicSentence] = []
    claims: list[PublicClaim] = []
    for index, (key, item) in enumerate(pairs):
        if limit is not None and index >= limit:
            break
        paper_id = f"qasper_{item.get('id') or key or index}"
        text = "\n\n".join(
            paragraph
            for section in item.get("full_text", [])
            for paragraph in section.get("paragraphs", [])
            if paragraph
        )
        papers.append(
            PublicPaper(
                paper_id=paper_id,
                title=str(item.get("title") or ""),
                text=text,
            )
        )
        sentences.extend(_sentence_rows(paper_id, text))
        for qa in item.get("qas", []):
            claims.append(
                PublicClaim(
                    claim_id=str(qa.get("question_id") or f"{paper_id}_q{len(claims)}"),
                    text=str(qa.get("question") or ""),
                    gold_paper_ids=(paper_id,),
                    evidence_level="paragraph",
                )
            )

    return PublicDataset(
        name="qasper",
        papers=papers,
        sentences=sentences,
        claims=claims,
        evidence_level="paragraph",
        source=str(path),
    )


def sentence_ids_by_paper(dataset: PublicDataset) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for sentence in dataset.sentences:
        result.setdefault(sentence.paper_id, []).append(sentence.sentence_id)
    return result


def iter_claims(dataset: PublicDataset) -> Iterable[PublicClaim]:
    return iter(dataset.claims)
