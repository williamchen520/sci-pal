"""Bounded citation-graph expansion with explicit budget accounting.

Design points carried over from ``nature-academic-search`` (MIT, wp-a) ``graph.py``:

- every edge is stored as ``citing -> cited`` regardless of which direction we
  queried, so downstream consumers never have to guess;
- ``observed_by`` records which sources saw an edge;
- a missing source edge is a *gap*, not evidence that no relation exists;
- truncation is reported (``truncated`` / ``truncation_reason``) instead of
  silently returning a partial graph.

Adapted to SciPal: the caller injects ``fetch_relations`` (a callable over the
local paper graph or an external adapter), so this module has no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from services.records.provenance import stable_record_id

RELATIONS = frozenset({"references", "cited_by", "both"})

#: Which identifier to send to each source, in priority order.
DEFAULT_SOURCE_IDENTIFIERS: dict[str, tuple[str, ...]] = {
    "openalex": ("openalex_id", "doi"),
    "crossref": ("doi",),
    "pubmed": ("pmid",),
    "europe_pmc": ("pmid", "pmcid"),
    "semantic_scholar": ("semantic_scholar_id", "doi", "arxiv_id"),
    "local": ("doi", "pmid", "pmcid"),
}

COVERAGE_NOTES = (
    "Missing source edges are not evidence that no citation relation exists.",
    "Citation relations do not measure evidence quality or causality.",
)

#: ``fetch_relations(identifier, relation, rows, source) -> payload | None``.
#: ``payload`` maps "references"/"cited_by" to a sequence of record mappings;
#: returning ``None`` means this source cannot provide edges.
RelationFetcher = Callable[[str, str, int, str], Mapping[str, Any] | None]


def build_citation_graph(
    seed: Mapping[str, Any],
    *,
    fetch_relations: RelationFetcher,
    relation: str = "both",
    depth: int = 1,
    rows: int = 20,
    sources: Sequence[str] | None = None,
    max_nodes: int = 100,
    max_edges: int = 200,
) -> dict[str, Any]:
    """Expand a bounded citation neighbourhood around ``seed``."""
    _validate(relation, depth, rows, max_nodes, max_edges)

    seed_node = _node(seed)
    seed_id = str(seed_node["record_id"])
    nodes: dict[str, dict[str, Any]] = {seed_id: seed_node}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    selected = list(dict.fromkeys(sources or list(DEFAULT_SOURCE_IDENTIFIERS)))

    queried: list[str] = []
    succeeded: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    frontier = [seed_node]
    truncated = False
    truncation_reason: str | None = None
    depth_completed = 0

    requested = ["references", "cited_by"] if relation == "both" else [relation]

    for level in range(1, depth + 1):
        next_frontier: dict[str, dict[str, Any]] = {}
        for current in sorted(frontier, key=lambda item: str(item["record_id"])):
            current_id = str(current["record_id"])
            for source in selected:
                identifier = _identifier_for_source(current, source)
                if not identifier:
                    _skip(skipped, source, "missing_source_identifier")
                    continue
                if source not in queried:
                    queried.append(source)
                try:
                    payload = fetch_relations(identifier, relation, rows, source)
                except Exception as exc:  # noqa: BLE001 - reported per source
                    errors.append(
                        {"source": source, "record_id": current_id, "error": str(exc)}
                    )
                    continue
                if payload is None:
                    _skip(skipped, source, "citation_edges_not_supported")
                    continue
                if source not in succeeded:
                    succeeded.append(source)

                for edge_relation in requested:
                    related_records = payload.get(edge_relation, [])
                    if not isinstance(related_records, Sequence) or isinstance(
                        related_records, (str, bytes)
                    ):
                        errors.append(
                            {
                                "source": source,
                                "record_id": current_id,
                                "error": f"Malformed {edge_relation} payload",
                            }
                        )
                        continue
                    for raw in related_records:
                        if not isinstance(raw, Mapping):
                            continue
                        related = _node(raw)
                        related_id = str(related["record_id"])
                        if related_id == current_id:
                            continue
                        if edge_relation == "references":
                            edge_from, edge_to = current_id, related_id
                        else:
                            edge_from, edge_to = related_id, current_id
                        key = (edge_from, edge_to, edge_relation)
                        if key not in edges and len(edges) >= max_edges:
                            truncated, truncation_reason = True, "max_edges"
                            break
                        if related_id not in nodes:
                            if len(nodes) >= max_nodes:
                                truncated, truncation_reason = True, "max_nodes"
                                break
                            nodes[related_id] = related
                            next_frontier[related_id] = related
                        else:
                            _merge_node(nodes[related_id], related)

                        if key in edges:
                            if source not in edges[key]["observed_by"]:
                                edges[key]["observed_by"].append(source)
                        else:
                            edges[key] = {
                                "from": edge_from,
                                "to": edge_to,
                                "relation": edge_relation,
                                "observed_by": [source],
                            }
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break
        depth_completed = level
        if truncated or not next_frontier:
            break
        frontier = list(next_frontier.values())

    ordered_edges = sorted(
        edges.values(), key=lambda item: (item["from"], item["to"], item["relation"])
    )
    for edge in ordered_edges:
        edge["observed_by"] = sorted(edge["observed_by"])
    ordered_nodes = [nodes[seed_id]] + [
        nodes[node_id] for node_id in sorted(nodes) if node_id != seed_id
    ]

    result: dict[str, Any] = {
        "schema_version": "1",
        "seed_record_id": seed_id,
        "direction": relation,
        "depth_requested": depth,
        "depth_completed": depth_completed,
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "sources_queried": queried,
        "sources_succeeded": succeeded,
        "sources_skipped": skipped,
        "errors": errors or None,
        "truncated": truncated,
        "coverage_notes": list(COVERAGE_NOTES),
    }
    if truncation_reason:
        result["truncation_reason"] = truncation_reason
    return result


def _validate(relation: str, depth: int, rows: int, max_nodes: int, max_edges: int) -> None:
    if relation not in RELATIONS:
        raise ValueError("relation must be 'references', 'cited_by' or 'both'")
    if depth not in {1, 2}:
        raise ValueError("depth must be 1 or 2")
    if not 1 <= rows <= 100:
        raise ValueError("rows must be between 1 and 100")
    if max_nodes < 2:
        raise ValueError("max_nodes must be at least 2")
    if max_edges < 1:
        raise ValueError("max_edges must be at least 1")


def _node(record: Mapping[str, Any]) -> dict[str, Any]:
    node = dict(record)
    node.setdefault("entity_type", "paper")
    node["record_id"] = stable_record_id(node)
    return node


def _merge_node(target: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    for key, value in incoming.items():
        if value not in (None, "", [], {}) and target.get(key) in (None, "", [], {}):
            target[key] = value


def _identifier_for_source(record: Mapping[str, Any], source: str) -> str:
    for field in DEFAULT_SOURCE_IDENTIFIERS.get(source, ()):
        value = record.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def _skip(skipped: list[dict[str, str]], source: str, reason: str) -> None:
    item = {"source": source, "reason": reason}
    if item not in skipped:
        skipped.append(item)
