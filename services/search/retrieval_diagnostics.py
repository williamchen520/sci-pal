"""
Retrieval diagnostics: transparent, inspectable retrieval pipeline.
V25.19 - Retrieval optimization

When diagnostics mode is enabled, the retriever captures every intermediate
stage of the retrieval pipeline and returns it alongside the final results.
This makes the retrieval process debuggable and optimizable, instead of a
black box.

Captured stages:
  1. query_router: which channels were selected and why
  2. query_expander: what query variants were generated
  3. fts_query: the enhanced FTS5 query string (entities, phrases, NEAR)
  4. vector_search: raw vector results with scores
  5. fts_search: raw FTS results with scores
  6. rrf_fusion: how scores were combined, which items appeared in both
  7. rerank: before/after reranking comparison
  8. mmr: before/after diversification, diversity metrics
  9. final: the final envelope

Usage:
    diag = RetrievalDiagnostics()
    diag.start("STAT1 interferon")
    diag.log("query_router", {"channels": ["qa", "figure"], ...})
    diag.log("vector_search", [...])
    ...
    report = diag.finish(final_results)
    # report is a dict with all stages + summary
"""
import time
from typing import Dict, List, Any, Optional


class RetrievalDiagnostics:
    """
    Capture and report the full retrieval pipeline for debugging.

    Usage pattern:
        diag = RetrievalDiagnostics(enabled=True)
        diag.start(query)
        with diag.stage("vector_search"):
            results = do_vector_search()
            diag.set_result("vector_search", results)
        ...
        report = diag.finish(final_envelope)
    """

    def __init__(self, enabled: bool = False, max_items_per_stage: int = 10):
        self.enabled = enabled
        self.max_items = max_items_per_stage
        self.query = ""
        self.start_time = 0.0
        self.stages: Dict[str, Dict] = {}
        self.stage_order: List[str] = []
        self._current_stage: Optional[str] = None
        self._stage_start: float = 0.0

    def start(self, query: str):
        """Begin a new diagnostic capture."""
        if not self.enabled:
            return
        self.query = query
        self.start_time = time.time()
        self.stages = {}
        self.stage_order = []

    def stage(self, name: str):
        """
        Context manager for timing a stage.
        Usage: with diag.stage("vector_search"): ...
        """
        self._current_stage = name
        self._stage_start = time.time()
        if name not in self.stage_order:
            self.stage_order.append(name)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self._current_stage:
            elapsed = time.time() - self._stage_start
            if self._current_stage not in self.stages:
                self.stages[self._current_stage] = {}
            self.stages[self._current_stage]["elapsed_ms"] = round(elapsed * 1000, 2)
            self._current_stage = None

    def mark(self, name: str, elapsed_ms: float) -> None:
        """Record timing for a phase measured outside :meth:`stage`."""
        if not self.enabled:
            return
        if name not in self.stages:
            self.stages[name] = {}
            self.stage_order.append(name)
        self.stages[name]["elapsed_ms"] = round(float(elapsed_ms), 2)

    def log(self, stage: str, key: str, value: Any):
        """Log a key-value pair for a stage."""
        if not self.enabled:
            return
        if stage not in self.stages:
            self.stages[stage] = {}
            self.stage_order.append(stage)
        self.stages[stage][key] = value

    def set_result(self, stage: str, results: List[Dict],
                   text_key: str = "text", score_key: str = "score"):
        """
        Log a list of results for a stage, truncated to max_items and
        summarized (text preview, score, paper_id).
        """
        if not self.enabled:
            return
        if stage not in self.stages:
            self.stages[stage] = {}
            self.stage_order.append(stage)

        summarized = []
        for i, r in enumerate(results[:self.max_items]):
            item = {
                "rank": i + 1,
                "score": round(float(r.get(score_key, r.get("rrf_score", 0))), 4),
                "paper_id": r.get("paper_id", r.get("metadata", {}).get("paper_id", "?")),
                "text_preview": (r.get(text_key, "") or "")[:120].replace("\n", " "),
            }
            # Include para_id if present
            if "para_id" in r:
                item["para_id"] = r["para_id"]
            summarized.append(item)

        self.stages[stage]["results"] = summarized
        self.stages[stage]["total_count"] = len(results)

    def log_rrf_details(self, vector_results: List[Dict],
                         fts_results: List[Dict],
                         fused: List[Dict]):
        """
        Log detailed RRF fusion information: which items appeared in both
        channels, their individual ranks, and the fused score.
        """
        if not self.enabled:
            return

        vector_ids = {r["para_id"]: i + 1 for i, r in enumerate(vector_results)}
        fts_ids = {r["para_id"]: i + 1 for i, r in enumerate(fts_results)}

        both = set(vector_ids.keys()) & set(fts_ids.keys())
        vector_only = set(vector_ids.keys()) - set(fts_ids.keys())
        fts_only = set(fts_ids.keys()) - set(vector_ids.keys())

        details = {
            "vector_count": len(vector_results),
            "fts_count": len(fts_results),
            "overlap_count": len(both),
            "vector_only_count": len(vector_only),
            "fts_only_count": len(fts_only),
            "overlap_items": [
                {
                    "para_id": pid,
                    "vector_rank": vector_ids[pid],
                    "fts_rank": fts_ids[pid],
                }
                for pid in list(both)[:10]
            ],
            "fused_top": [
                {
                    "rank": i + 1,
                    "para_id": r.get("para_id"),
                    "rrf_score": round(r.get("rrf_score", 0), 4),
                    "in_vector": r.get("para_id") in vector_ids,
                    "in_fts": r.get("para_id") in fts_ids,
                }
                for i, r in enumerate(fused[:10])
            ],
        }
        self.log("rrf_fusion", "details", details)

    def log_rerank_comparison(self, before: List[Dict], after: List[Dict],
                               score_key_before: str = "rrf_score",
                               score_key_after: str = "rerank_score"):
        """Log before/after reranking comparison."""
        if not self.enabled:
            return

        before_ids = [r.get("para_id") for r in before]
        after_ids = [r.get("para_id") for r in after]

        # Count position changes
        position_changes = 0
        for i, pid in enumerate(after_ids):
            if pid in before_ids:
                old_pos = before_ids.index(pid)
                if old_pos != i:
                    position_changes += 1

        comparison = {
            "candidate_count": len(before),
            "final_count": len(after),
            "position_changes": position_changes,
            "top5_before": [r.get("para_id") for r in before[:5]],
            "top5_after": [r.get("para_id") for r in after[:5]],
            "score_range_before": {
                "min": round(min((r.get(score_key_before, 0) for r in before), default=0), 4),
                "max": round(max((r.get(score_key_before, 0) for r in before), default=0), 4),
            },
            "score_range_after": {
                "min": round(min((r.get(score_key_after, 0) for r in after), default=0), 4),
                "max": round(max((r.get(score_key_after, 0) for r in after), default=0), 4),
            },
        }
        self.log("rerank", "comparison", comparison)

    def finish(self, final_results: Optional[Dict] = None) -> Dict:
        """
        Finish the diagnostic capture and return the full report.

        Returns:
            A dict with:
              - query: the original query
              - total_time_ms: total pipeline time
              - stages: ordered dict of stage data
              - summary: high-level metrics
              - final: final results (if provided)
        """
        if not self.enabled:
            return {"enabled": False}

        total_time = round((time.time() - self.start_time) * 1000, 2)

        # Build summary
        summary = {
            "query": self.query,
            "total_time_ms": total_time,
            "stages_executed": len(self.stage_order),
            "stage_times": {
                stage: self.stages.get(stage, {}).get("elapsed_ms", "?")
                for stage in self.stage_order
            },
        }

        # Add result counts per stage
        for stage in self.stage_order:
            if "total_count" in self.stages.get(stage, {}):
                summary[f"{stage}_count"] = self.stages[stage]["total_count"]

        report = {
            "enabled": True,
            "query": self.query,
            "total_time_ms": total_time,
            "stage_order": self.stage_order,
            "stages": self.stages,
            "summary": summary,
        }
        if final_results is not None:
            report["final"] = final_results

        return report

    def format_text_report(self, report: Dict) -> str:
        """
        Format a diagnostic report as a human-readable text block.
        Useful for logging or CLI output.
        """
        if not report.get("enabled"):
            return "[diagnostics disabled]"

        lines = [
            "=" * 60,
            f"🔍 Retrieval Diagnostics: {report['query']}",
            f"   Total: {report['total_time_ms']}ms | "
            f"Stages: {report['summary']['stages_executed']}",
            "=" * 60,
        ]

        for stage in report["stage_order"]:
            data = report["stages"].get(stage, {})
            elapsed = data.get("elapsed_ms", "?")
            count = data.get("total_count", "")
            count_str = f" ({count} results)" if count else ""
            lines.append(f"\n── {stage} [{elapsed}ms]{count_str} ──")

            # Special formatting for known stages
            if stage == "query_router":
                if "channels" in data:
                    lines.append(f"   Channels: {data['channels']}")
                if "primary" in data:
                    lines.append(f"   Primary intent: {data['primary']}")

            elif stage == "query_expander":
                if "variants" in data:
                    for i, v in enumerate(data["variants"], 1):
                        lines.append(f"   [{i}] {v}")

            elif stage == "fts_query":
                if "fts_query" in data:
                    lines.append(f"   Query: {data['fts_query']}")
                if "entities" in data:
                    lines.append(f"   Entities: {data['entities']}")
                if "phrases" in data:
                    lines.append(f"   Phrases: {data['phrases']}")

            elif stage == "rrf_fusion":
                if "details" in data:
                    d = data["details"]
                    lines.append(f"   Vector: {d['vector_count']} | FTS: {d['fts_count']} | "
                                 f"Overlap: {d['overlap_count']}")

            elif "results" in data:
                for r in data["results"][:5]:
                    lines.append(f"   [{r['rank']}] score={r['score']:.4f} "
                                 f"paper={r.get('paper_id', '?')[:12]}")
                    lines.append(f"        {r['text_preview']}...")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    diag = RetrievalDiagnostics(enabled=True)
    diag.start("How does STAT1 regulate interferon?")

    with diag.stage("query_router"):
        diag.log("query_router", "channels", ["qa", "papers"])
        diag.log("query_router", "primary", "qa")

    with diag.stage("query_expander"):
        diag.log("query_expander", "variants", [
            "How does STAT1 regulate interferon?",
            "STAT1 regulate interferon immune response",
            "STAT1 interferon",
        ])

    with diag.stage("vector_search"):
        fake_results = [
            {"para_id": f"p{i}", "text": f"STAT1 interferon paragraph {i}",
             "score": 0.9 - i * 0.05, "paper_id": f"paper_{i % 3}"}
            for i in range(8)
        ]
        diag.set_result("vector_search", fake_results, score_key="score")

    with diag.stage("fts_search"):
        fake_results = [
            {"para_id": f"p{i*2}", "text": f"FTS result {i}",
             "score": 0.85 - i * 0.04, "paper_id": f"paper_{i % 3}"}
            for i in range(6)
        ]
        diag.set_result("fts_search", fake_results, score_key="score")

    report = diag.finish()
    print(diag.format_text_report(report))
