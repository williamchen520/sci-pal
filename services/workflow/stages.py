"""Stage implementations for the review workflow.

This batch wires the three stages that do not need models:

- ``plan``    validate the outline and write ``plan.json`` (approval input);
- ``store``   persist the review record (adapter injected; default is a JSON
              store so the pipeline runs before the DB adapter exists);
- ``export``  write deliverables (adapter injected; default copies Markdown).

``retrieve`` / ``evidence`` / ``draft`` / ``verify`` stay unimplemented here on
purpose: they need the retrieval stack and the LLM, and will be wired one at a
time with their own tests.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from services.workflow.runner import write_artifact
from services.workflow.types import StageContext, StageResult

SaveReview = Callable[[Mapping[str, Any], StageContext], Mapping[str, Any]]
ExportReview = Callable[[Mapping[str, Any], StageContext], list[str]]
Retrieve = Callable[[list[dict[str, Any]], str, int, StageContext], Mapping[str, Any]]
Verify = Callable[[Mapping[str, Any], StageContext], Mapping[str, Any]]
Extract = Callable[[Mapping[str, Any], StageContext], Mapping[str, Any]]
Draft = Callable[[Mapping[str, Any], Mapping[str, Any], StageContext], Mapping[str, Any]]


def build_plan_stage() -> Callable[[StageContext], StageResult]:
    """Validate the outline and freeze the run plan."""

    def stage(context: StageContext) -> StageResult:
        sections = _sections(context.spec.metadata.get("outline"))
        if not sections:
            return _failed("invalid_input", "outline has no sections")
        plan = {
            "schema_version": "1",
            "run_id": context.run_id,
            "topic": context.spec.topic,
            "workflow": context.spec.workflow,
            "sections": sections,
            "stages": [
                {"name": name, "expected_artifacts": _expected_artifacts(name)}
                for name in context.spec.stages
            ],
            "limits": dict(context.spec.limits),
            "created_at": _now(),
        }
        write_artifact(context, "plan.json", plan)
        return StageResult(artifacts=["plan.json"], metrics={"sections": len(sections)})

    return stage


def build_retrieve_stage(retrieve: Retrieve | None = None) -> Callable[[StageContext], StageResult]:
    """Search and assign papers per plan section. Reads ``plan.json``.

    The underlying ``search_and_assign_papers`` call is synchronous and can run
    for minutes; the runner belongs off the request thread (CLI or worker), not
    inside an HTTP handler.
    """
    finder = retrieve or _default_retrieve

    def stage(context: StageContext) -> StageResult:
        plan = _read_json(context.run_dir / "plan.json")
        if plan is None:
            return _failed("invalid_input", "plan.json is missing; plan must run first")
        sections = plan.get("sections") or []
        if not sections:
            return _failed("invalid_input", "plan has no sections")

        max_papers = int(context.spec.limits.get("max_papers", 100))
        try:
            payload = dict(finder(sections, context.spec.topic, max_papers, context))
        except Exception as exc:  # noqa: BLE001 - reported as a stage error
            return _failed("upstream", f"retrieval failed: {exc}")

        write_artifact(context, "retrieve.json", payload)
        return StageResult(
            artifacts=["retrieve.json"],
            metrics={
                "sections": len(payload.get("sections") or []),
                "papers": len(payload.get("papers") or []),
            },
        )

    return stage


def build_draft_stage(draft: Draft | None = None) -> Callable[[StageContext], StageResult]:
    """Write the draft and emit ``review.json`` + ``draft.md``.

    ``review.json`` is the interface consumed by the verify stage, so its shape
    (sentences + evidence_cards) is part of the contract, not an implementation
    detail.
    """
    writer = draft or _default_draft

    def stage(context: StageContext) -> StageResult:
        plan = _read_json(context.run_dir / "plan.json")
        evidence = _read_json(context.run_dir / "evidence.json")
        if plan is None:
            return _failed("invalid_input", "plan.json is missing; plan must run first")
        if evidence is None:
            return _failed("invalid_input", "evidence.json is missing; evidence must run first")

        try:
            payload = dict(writer(plan, evidence, context))
        except ValueError as exc:
            return _failed("invalid_input", str(exc))
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            return _failed("upstream", f"draft failed: {exc}")

        review = {
            "topic": payload.get("topic") or context.spec.topic,
            "sections": payload.get("sections") or [],
            "sentences": payload.get("sentences") or [],
            "evidence_cards": payload.get("evidence_cards") or {},
            "markdown": str(payload.get("markdown") or ""),
        }
        markdown = review["markdown"]
        write_artifact(context, "review.json", review)
        write_artifact(context, "draft.md", markdown)

        return StageResult(
            artifacts=["review.json", "draft.md"],
            metrics={
                "sections": len(review["sections"]),
                "sentences": len(review["sentences"]),
                "words": len(markdown.split()),
            },
        )

    return stage


def build_verify_stage(verify: Verify | None = None) -> Callable[[StageContext], StageResult]:
    """Deterministic citation check. Reads ``review.json``, writes ``verify.json``."""
    checker = verify or _default_verify

    def stage(context: StageContext) -> StageResult:
        review = _read_json(context.run_dir / "review.json")
        if review is None:
            return _failed("invalid_input", "review.json is missing; draft must run first")

        try:
            payload = dict(checker(review, context))
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            return _failed("internal", f"verification failed: {exc}")

        write_artifact(context, "verify.json", payload)
        stats = payload.get("stats") or {}
        metrics = {
            key: stats.get(key)
            for key in ("total_sentences", "verified", "rejected", "pass_rate")
            if key in stats
        }
        return StageResult(artifacts=["verify.json"], metrics=metrics)

    return stage


def build_evidence_stage(extract: Extract | None = None) -> Callable[[StageContext], StageResult]:
    """Turn retrieved paragraphs into evidence cards (simplified path, no LLM)."""
    extractor = extract or _default_extract

    def stage(context: StageContext) -> StageResult:
        payload = _read_json(context.run_dir / "retrieve.json")
        if payload is None:
            return _failed("invalid_input", "retrieve.json is missing; retrieve must run first")

        provided = payload.get("evidence_cards")
        if isinstance(provided, list) and provided:
            # retrieve already produced cards (search_and_assign_papers does this);
            # extraction would only duplicate them.
            cards = [dict(item) for item in provided if isinstance(item, Mapping)]
            result = {"cards": cards, "count": len(cards), "source": "retrieve"}
            write_artifact(context, "evidence.json", result)
            return StageResult(artifacts=["evidence.json"], metrics={"cards": len(cards)})

        try:
            result = dict(extractor(payload, context))
        except ValueError as exc:
            return _failed("invalid_input", str(exc))
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            return _failed("upstream", f"evidence extraction failed: {exc}")

        write_artifact(context, "evidence.json", result)
        cards = result.get("cards") or []
        return StageResult(artifacts=["evidence.json"], metrics={"cards": len(cards)})

    return stage


def build_store_stage(save_review: SaveReview | None = None) -> Callable[[StageContext], StageResult]:
    """Persist the reviewed draft. Reads ``review.json``, writes ``store.json``."""
    saver = save_review or _default_save_review

    def stage(context: StageContext) -> StageResult:
        review = _read_json(context.run_dir / "review.json")
        if review is None:
            return _failed("invalid_input", "review.json is missing; draft/verify must run first")
        record = saver(review, context)
        write_artifact(context, "store.json", dict(record))
        return StageResult(
            artifacts=["store.json"],
            metrics={"review_id": record.get("review_id")},
        )

    return stage


def build_export_stage(export_review: ExportReview | None = None) -> Callable[[StageContext], StageResult]:
    """Export deliverables. Reads ``store.json``, writes under ``exports/``."""
    exporter = export_review or _markdown_export

    def stage(context: StageContext) -> StageResult:
        record = _read_json(context.run_dir / "store.json")
        if record is None:
            return _failed("invalid_input", "store.json is missing; store must run first")
        artifacts = exporter(record, context)
        return StageResult(artifacts=list(artifacts), metrics={"files": len(artifacts)})

    return stage


# ---------------------------------------------------------------------------
# Default adapters (replaceable without touching the runner or the stages)
# ---------------------------------------------------------------------------


def _default_retrieve(
    sections: list[dict[str, Any]],
    topic: str,
    max_papers: int,
    context: StageContext,
) -> dict[str, Any]:
    """Adapter over the existing review pipeline (models load on first call)."""
    from services.review.review_generator import search_and_assign_papers

    retriever = context.services.get("retriever") or _build_retriever()
    outline, papers = search_and_assign_papers(
        outline={"sections": sections},
        topic=topic,
        max_papers=max_papers,
        retriever=retriever,
    )
    return {
        "sections": outline.get("sections", sections),
        "papers": papers,
        "evidence_cards": outline.get("evidence_cards") or [],
        "max_papers": max_papers,
    }


def _build_retriever() -> Any:
    from services.search.unified_retriever import UnifiedRetriever

    return UnifiedRetriever(rerank=True, routing=True, expand=True, graph_expand=True)


def _default_draft(
    plan: Mapping[str, Any],
    evidence: Mapping[str, Any],
    context: StageContext,
) -> dict[str, Any]:
    """Build the domain inputs and run the existing draft writer."""
    from services.review.review_generator import ReviewGenerator

    generator = context.services.get("generator")
    if generator is None:
        from services.review.llm_client import LLMClient

        generator = ReviewGenerator(LLMClient())

    retrieve = _read_json(context.run_dir / "retrieve.json")
    outline, cards = _draft_inputs(plan, retrieve, evidence, context.spec.topic)
    draft = generator._write_draft(
        context.spec.topic,
        outline,
        cards,
        review_type=str(context.spec.limits.get("review_type", "narrative")),
        language=str(context.spec.limits.get("language", "en")),
    )
    return _serialize_draft(draft)


def _draft_inputs(
    plan: Mapping[str, Any],
    retrieve: Mapping[str, Any] | None,
    evidence: Mapping[str, Any],
    topic: str,
):
    from services.review.models import EvidenceCard, ReviewOutline, ReviewSection

    cards: dict[str, Any] = {}
    for item in evidence.get("cards") or []:
        if isinstance(item, Mapping) and item.get("evidence_id"):
            cards[str(item["evidence_id"])] = EvidenceCard(**dict(item))
    if not cards:
        raise ValueError("evidence.json has no evidence cards")

    assignments: dict[str, list[str]] = {}
    if isinstance(retrieve, Mapping):
        for item in retrieve.get("sections") or []:
            if not isinstance(item, Mapping):
                continue
            section_id = str(item.get("id") or item.get("section_id") or "")
            if section_id:
                assignments[section_id] = [
                    str(value) for value in item.get("assigned_evidence_ids") or []
                ]

    plan_sections = [item for item in plan.get("sections") or [] if isinstance(item, Mapping)]
    sections = []
    for index, item in enumerate(plan_sections, start=1):
        section_id = str(item.get("id") or f"sec-{index:02d}")
        assigned = [eid for eid in assignments.get(section_id, []) if eid in cards]
        if not assigned:
            if len(plan_sections) > 1:
                raise ValueError(
                    f"section {section_id} has no assigned evidence; "
                    "retrieve must provide assigned_evidence_ids"
                )
            assigned = list(cards)
        sections.append(
            ReviewSection(
                section_id=section_id,
                title=str(item.get("title") or section_id),
                order=index,
                assigned_evidence_ids=assigned,
            )
        )

    return ReviewOutline(topic=topic, sections=sections), cards


def _serialize_draft(draft: Any) -> dict[str, Any]:
    return {
        "topic": draft.topic,
        "sections": [
            {"section_id": section.section_id, "title": section.title}
            for section in draft.outline.sections
        ],
        "sentences": [sentence.model_dump(mode="json") for sentence in draft.sentences],
        "evidence_cards": {
            evidence_id: card.model_dump(mode="json")
            for evidence_id, card in draft.evidence_cards.items()
        },
        "markdown": _render_markdown(draft),
    }


def _render_markdown(draft: Any) -> str:
    parts = [f"# {draft.topic}\n"]
    for section in draft.outline.sections:
        parts.append(f"\n## {section.title}\n")
        for sentence in draft.sentences:
            if sentence.section_id == section.section_id:
                parts.append(f"{sentence.text.strip()} ")
    return "".join(parts).strip() + "\n"


def _rebuild_draft(review: Mapping[str, Any], context: StageContext):
    """Rebuild ReviewDraft from the JSON contract (used by verify and store)."""
    from services.review.models import (
        EvidenceCard,
        ReviewDraft,
        ReviewOutline,
        ReviewSection,
        ReviewSentence,
    )

    plan = _read_json(context.run_dir / "plan.json") or {}
    sections = [
        ReviewSection(section_id=item["id"], title=item["title"], order=index)
        for index, item in enumerate(plan.get("sections") or [], start=1)
    ]
    topic = str(review.get("topic") or context.spec.topic)
    return ReviewDraft(
        topic=topic,
        outline=ReviewOutline(topic=topic, sections=sections),
        sentences=[ReviewSentence(**item) for item in review.get("sentences") or []],
        evidence_cards={
            evidence_id: EvidenceCard(**card)
            for evidence_id, card in (review.get("evidence_cards") or {}).items()
        },
    )


def _default_verify(review: Mapping[str, Any], context: StageContext) -> dict[str, Any]:
    """Rebuild the domain objects and run the deterministic citation check."""
    from services.review.citation_verifier import CitationVerifier

    draft = _rebuild_draft(review, context)
    verified, warnings = CitationVerifier().verify(draft)
    return {
        "topic": draft.topic,
        "stats": verified.stats(),
        "warnings": warnings,
        "sentences": [sentence.model_dump(mode="json") for sentence in verified.sentences],
    }


def _default_extract(payload: Mapping[str, Any], context: StageContext) -> dict[str, Any]:
    """Simplified evidence extraction: one card per paragraph, no LLM call."""
    from services.review.evidence_extractor import EvidenceExtractor

    paragraphs = _paragraphs_from_retrieve(payload)
    if not paragraphs:
        raise ValueError(
            "retrieve.json has neither paragraphs nor paper abstracts to extract evidence from"
        )

    extractor = context.services.get("extractor") or EvidenceExtractor(None)
    cards = extractor.extract_from_paragraphs(
        paragraphs,
        topic=context.spec.topic,
        language=str(context.spec.limits.get("language", "en")),
    )
    return {
        "cards": [card.model_dump(mode="json") for card in cards],
        "count": len(cards),
    }


def _paragraphs_from_retrieve(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Prefer real paragraphs; fall back to abstracts so the stage can still run."""
    paragraphs = payload.get("paragraphs")
    if isinstance(paragraphs, list) and paragraphs:
        usable = [
            dict(item)
            for item in paragraphs
            if isinstance(item, Mapping)
            and item.get("text")
            and item.get("paper_id")
            and item.get("para_id")
        ]
        if usable:
            return usable

    derived: list[dict[str, Any]] = []
    for paper in payload.get("papers") or []:
        if not isinstance(paper, Mapping):
            continue
        abstract = str(paper.get("abstract") or "").strip()
        paper_id = str(paper.get("paper_id") or paper.get("id") or "").strip()
        if not abstract or not paper_id:
            continue
        derived.append(
            {
                "paper_id": paper_id,
                "para_id": f"{paper_id}::abstract",
                "text": abstract,
                "paper_title": paper.get("title", ""),
                "section_l1": "abstract",
                "source_type": "abstract",
            }
        )
    return derived


def _default_save_review(review: Mapping[str, Any], context: StageContext) -> dict[str, Any]:
    """Persist into the in-process ReviewStore *and* the durable reviews table."""
    from services.review.models import ReviewOutput
    from services.review.review_repository import ReviewRepository
    from services.review.review_store import get_review_store

    draft = _rebuild_draft(review, context)
    markdown = str(review.get("markdown") or "") or _render_markdown(draft)
    output = ReviewOutput(
        topic=draft.topic,
        markdown=markdown,
        references=list(review.get("references") or []),
        stats=dict(review.get("stats") or draft.stats()),
        warnings=list(review.get("warnings") or []),
    )
    review_id = get_review_store().store(
        output, draft, list(draft.evidence_cards.values())
    )

    db_path = context.services.get("db_path") or _default_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    ReviewRepository(db_path).save(
        review_id=review_id,
        run_id=context.run_id,
        topic=draft.topic,
        markdown=markdown,
        stats=output.stats,
        references=output.references,
        warnings=output.warnings,
    )
    return {
        "review_id": review_id,
        "topic": draft.topic,
        "stored_at": _now(),
        "stats": output.stats,
        "db_path": str(db_path),
    }


def _default_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "research.db"


def _markdown_export(record: Mapping[str, Any], context: StageContext) -> list[str]:
    """Write the reviewed Markdown plus a small manifest under ``exports/``."""
    source = context.run_dir / "draft.md"
    markdown = source.read_text(encoding="utf-8") if source.exists() else ""

    exports = context.run_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    (exports / "review.md").write_text(markdown, encoding="utf-8")
    (exports / "metadata.json").write_text(
        json.dumps(
            {
                "review_id": record.get("review_id"),
                "topic": record.get("topic"),
                "exported_at": _now(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ["exports/review.md", "exports/metadata.json"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sections(outline: Any) -> list[dict[str, Any]]:
    if not isinstance(outline, Mapping):
        return []
    raw = outline.get("sections")
    if not isinstance(raw, list):
        return []

    sections: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        section_id = str(item.get("id") or item.get("section_id") or f"sec-{index:02d}")
        keywords = item.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [part for part in re.split(r"[,;，；]", keywords) if part.strip()]
        sections.append(
            {
                "id": section_id,
                "title": title,
                "keywords": [str(word).strip() for word in keywords if str(word).strip()],
            }
        )
    return sections


def _expected_artifacts(stage: str) -> list[str]:
    return {
        "plan": ["plan.json"],
        "retrieve": ["retrieve.json"],
        "evidence": ["evidence.json"],
        "draft": ["draft.md", "review.json"],
        "verify": ["verify.json"],
        "store": ["store.json"],
        "export": ["exports/review.md"],
    }.get(stage, [])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _failed(kind: str, message: str) -> StageResult:
    return StageResult(
        status="failed",
        errors=[{"kind": kind, "message": message, "retryable": False}],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
