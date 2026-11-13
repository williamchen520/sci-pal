"""RAG control plane API: registry (R0) + plans/jobs (R1)."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, session

from services.rag_control.plans import (
    PlanError,
    approve_plan,
    cancel_plan,
    complete_job,
    create_plan,
    dispatch_plan,
    fail_job,
    get_job,
    get_plan,
    list_plans,
    heartbeat,
    lease_job,
)
from services.rag_control.adjudication import AdjudicationError, add_adjudication, add_conflict, get_multi, list_multi
from services.rag_control.agreement import agreement
from services.rag_control.finalization import FinalizationError, finalize, get_finalization
from services.rag_control.assignments import AssignmentError, assign, complete_assignment, list_assignments
from services.rag_control.audit import list_adjudications, list_conflicts, ro_crate
from services.rag_control.gateway import GatewayError, multi_query, query as gateway_query
from services.rag_control.ledger import LedgerError, append_artifact, append_evidence, list_artifacts, list_evidence
from services.rag_control.models import ModelError, get_model, list_bindings, list_models, register_binding
from services.rag_control.registry import check_health, get_provider, list_providers
from services.tenancy.service import authorize


def build_rag_control_blueprint() -> Blueprint:
    bp = Blueprint("rag_control", __name__)

    def _worker_ok() -> bool:
        expected = os.environ.get("SCIPAL_RAG_WORKER_TOKEN", "").strip()
        supplied = request.headers.get("X-SCIPAL-RAG-Worker-Token", "").strip()
        return bool(expected and supplied and supplied == expected)

    def _human() -> str | None:
        # A request carrying the internal agent token cannot self-approve.
        if request.headers.get("X-SCIPAL-Internal-Token"):
            return None
        return session.get("user_id")

    @bp.get("/api/rag/providers")
    def providers():
        return jsonify({"providers": list_providers()})

    @bp.get("/api/rag/providers/<rag_id>")
    def provider(rag_id: str):
        value = get_provider(rag_id)
        if not value:
            return jsonify({"error": "provider not found"}), 404
        return jsonify(value)

    @bp.get("/api/rag/providers/<rag_id>/health")
    def health(rag_id: str):
        value = check_health(rag_id)
        if not value:
            return jsonify({"error": "provider not found"}), 404
        return jsonify(value)

    @bp.post("/api/rag/plans")
    def plan_create():
        body = request.get_json(silent=True) or {}
        try:
            plan = create_plan(
                intent=str(body.get("intent") or ""),
                steps=body.get("steps") or [],
                created_by=session.get("user_id") or "internal",
            )
        except PlanError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(plan), 201

    @bp.get("/api/rag/plans/<plan_id>")
    def plan_get(plan_id: str):
        plan = get_plan(plan_id)
        if not plan:
            return jsonify({"error": "plan not found"}), 404
        return jsonify(plan)

    @bp.post("/api/rag/plans/<plan_id>/approve")
    def plan_approve(plan_id: str):
        user_id = _human()
        if not user_id:
            return jsonify({"error": "human approval required"}), 403
        body = request.get_json(silent=True) or {}
        try:
            plan = approve_plan(
                plan_id=plan_id,
                approved_by=user_id,
                plan_hash=str(body.get("plan_hash") or ""),
            )
        except PlanError as exc:
            return jsonify({"error": str(exc)}), 400
        if not plan:
            return jsonify({"error": "plan not found"}), 404
        return jsonify(plan)

    @bp.post("/api/rag/plans/<plan_id>/dispatch")
    def plan_dispatch(plan_id: str):
        try:
            plan = dispatch_plan(plan_id=plan_id)
        except PlanError as exc:
            return jsonify({"error": str(exc)}), 400
        if not plan:
            return jsonify({"error": "plan not found"}), 404
        return jsonify(plan)

    @bp.post("/api/rag/plans/<plan_id>/cancel")
    def plan_cancel(plan_id: str):
        if not cancel_plan(plan_id):
            return jsonify({"error": "plan not cancellable"}), 404
        return jsonify({"ok": True, "plan_id": plan_id})

    @bp.get("/api/rag/jobs/<job_id>")
    def job_get(job_id: str):
        job = get_job(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify(job)

    @bp.post("/api/rag/jobs/lease")
    def job_lease():
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        body = request.get_json(silent=True) or {}
        job = lease_job(
            worker_id=str(body.get("worker_id") or "").strip(),
            lease_seconds=int(body.get("lease_seconds") or 60),
        )
        if not job:
            return jsonify({"job": None})
        return jsonify({"job": job})

    @bp.post("/api/rag/jobs/<job_id>/heartbeat")
    def job_heartbeat(job_id: str):
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        body = request.get_json(silent=True) or {}
        ok = heartbeat(
            job_id=job_id,
            worker_id=str(body.get("worker_id") or "").strip(),
            lease_seconds=int(body.get("lease_seconds") or 60),
        )
        return jsonify({"ok": ok})

    @bp.post("/api/rag/jobs/<job_id>/complete")
    def job_complete(job_id: str):
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        body = request.get_json(silent=True) or {}
        result = complete_job(
            job_id=job_id,
            worker_id=str(body.get("worker_id") or "").strip(),
            payload=body,
            evidence=body.get("evidence") or [],
        )
        if not result:
            return jsonify({"error": "job not owned by worker"}), 409
        return jsonify(result)

    @bp.post("/api/rag/jobs/<job_id>/fail")
    def job_fail(job_id: str):
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        body = request.get_json(silent=True) or {}
        result = fail_job(
            job_id=job_id,
            worker_id=str(body.get("worker_id") or "").strip(),
            error=str(body.get("error") or "worker failed"),
        )
        if not result:
            return jsonify({"error": "job not owned by worker"}), 409
        return jsonify(result)

    @bp.get("/api/rag/models")
    def models():
        return jsonify({"models": list_models()})

    @bp.get("/api/rag/models/<model_id>")
    def model(model_id: str):
        value = get_model(model_id)
        if not value:
            return jsonify({"error": "model not found"}), 404
        return jsonify(value)

    @bp.get("/api/rag/index-bindings")
    def bindings():
        return jsonify(
            {
                "bindings": list_bindings(
                    rag_id=str(request.args.get("rag_id") or ""),
                    library_id=str(request.args.get("library_id") or ""),
                )
            }
        )

    @bp.post("/api/rag/index-bindings")
    def binding_register():
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        body = request.get_json(silent=True) or {}
        try:
            value = register_binding(
                rag_id=str(body.get("rag_id") or ""),
                library_id=str(body.get("library_id") or ""),
                index_name=str(body.get("index_name") or ""),
                embedding_model=str(body.get("embedding_model") or ""),
                dimension=body.get("dimension"),
                schema_version=int(body.get("schema_version") or 1),
                snapshot=str(body.get("snapshot") or ""),
                status=str(body.get("status") or "active"),
            )
        except ModelError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(value), 201

    @bp.get("/api/rag/runs/<run_id>/evidence")
    def evidence_list(run_id: str):
        return jsonify({"evidence": list_evidence(run_id)})

    @bp.post("/api/rag/runs/<run_id>/evidence")
    def evidence_append(run_id: str):
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        try:
            value = append_evidence(run_id, request.get_json(silent=True) or {})
        except LedgerError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify(value), 201

    @bp.get("/api/rag/runs/<run_id>/artifacts")
    def artifacts_list(run_id: str):
        return jsonify({"artifacts": list_artifacts(run_id)})

    @bp.post("/api/rag/runs/<run_id>/artifacts")
    def artifact_append(run_id: str):
        if not _worker_ok():
            return jsonify({"error": "worker token required"}), 403
        try:
            value = append_artifact(run_id, request.get_json(silent=True) or {})
        except LedgerError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(value), 201

    @bp.post("/api/rag/query")
    def rag_query():
        body = request.get_json(silent=True) or {}
        capability = str(body.get("capability") or "")
        try:
            if capability == "multi_search":
                result = multi_query(
                    rag_ids=body.get("rag_ids") or [],
                    library_id=str(body.get("library_id") or ""),
                    query_text=str(body.get("query") or ""),
                    top_k=int(body.get("top_k") or 10),
                    timeout=int(body.get("timeout") or 30),
                    created_by=session.get("user_id") or "internal",
                    workspace_id=session.get("workspace_id") or "ws_default",
                )
            else:
                result = gateway_query(
                    capability=capability,
                    library_id=str(body.get("library_id") or ""),
                    query_text=str(body.get("query") or ""),
                    top_k=int(body.get("top_k") or 10),
                    timeout=int(body.get("timeout") or 30),
                )
        except GatewayError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    @bp.get("/api/rag/plans")
    def plans_list():
        return jsonify(
            {
                "plans": list_plans(
                    status=str(request.args.get("status") or ""),
                    limit=int(request.args.get("limit") or 50),
                )
            }
        )

    @bp.get("/api/rag/multi")
    def multi_list():
        return jsonify({"multi_runs": list_multi()})

    @bp.get("/api/rag/multi/<multi_run_id>")
    def multi_get(multi_run_id: str):
        value = get_multi(multi_run_id)
        if not value:
            return jsonify({"error": "multi run not found"}), 404
        return jsonify(value)

    @bp.post("/api/rag/multi/<multi_run_id>/adjudications")
    def multi_adjudicate(multi_run_id: str):
        user_id = _human()
        if not user_id:
            return jsonify({"error": "human adjudication required"}), 403
        multi = get_multi(multi_run_id)
        if not multi:
            return jsonify({"error": "multi run not found"}), 404
        if not authorize(user_id, multi["workspace_id"], "review_evidence"):
            return jsonify({"error": "reviewer permission required"}), 403
        body = request.get_json(silent=True) or {}
        try:
            rag_id = str(body.get("rag_id") or "")
            value = add_adjudication(
                multi_run_id=multi_run_id,
                rag_id=rag_id,
                decision=str(body.get("decision") or ""),
                note=str(body.get("note") or ""),
                decided_by=user_id,
            )
            complete_assignment(multi_run_id=multi_run_id, rag_id=rag_id, reviewer_user_id=user_id)
        except AdjudicationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(value), 201

    @bp.post("/api/rag/multi/<multi_run_id>/conflicts")
    def multi_conflict(multi_run_id: str):
        user_id = _human()
        if not user_id:
            return jsonify({"error": "human conflict flag required"}), 403
        multi = get_multi(multi_run_id)
        if not multi:
            return jsonify({"error": "multi run not found"}), 404
        if not authorize(user_id, multi["workspace_id"], "review_evidence"):
            return jsonify({"error": "reviewer permission required"}), 403
        body = request.get_json(silent=True) or {}
        try:
            value = add_conflict(
                multi_run_id=multi_run_id,
                rag_id=str(body.get("rag_id") or ""),
                note=str(body.get("note") or ""),
                flagged_by=user_id,
            )
        except AdjudicationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(value), 201

    @bp.get("/api/rag/multi/<multi_run_id>/export.json")
    def multi_export(multi_run_id: str):
        value = get_multi(multi_run_id)
        if not value:
            return jsonify({"error": "multi run not found"}), 404
        response = jsonify(value)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{multi_run_id}.json"'
        )
        return response

    @bp.get("/api/rag/audit/adjudications")
    def audit_adjudications():
        return jsonify(
            {
                "adjudications": list_adjudications(
                    decision=str(request.args.get("decision") or ""),
                    rag_id=str(request.args.get("rag_id") or ""),
                    limit=int(request.args.get("limit") or 100),
                )
            }
        )

    @bp.get("/api/rag/audit/conflicts")
    def audit_conflicts():
        return jsonify(
            {
                "conflicts": list_conflicts(
                    rag_id=str(request.args.get("rag_id") or ""),
                    limit=int(request.args.get("limit") or 100),
                )
            }
        )

    @bp.get("/api/rag/multi/<multi_run_id>/export/ro-crate.zip")
    def multi_ro_crate(multi_run_id: str):
        blob = ro_crate(multi_run_id)
        if blob is None:
            return jsonify({"error": "multi run not found"}), 404
        from flask import Response

        return Response(
            blob,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{multi_run_id}.ro-crate.zip"'
            },
        )

    @bp.get("/api/rag/multi/<multi_run_id>/agreement")
    def multi_agreement(multi_run_id: str):
        value = agreement(multi_run_id)
        if not value:
            return jsonify({"error": "multi run not found"}), 404
        return jsonify(value)

    @bp.get("/api/rag/multi/<multi_run_id>/assignments")
    def assignments_list(multi_run_id: str):
        return jsonify({"assignments": list_assignments(multi_run_id)})

    @bp.post("/api/rag/multi/<multi_run_id>/assignments")
    def assignments_create(multi_run_id: str):
        user_id = _human()
        if not user_id:
            return jsonify({"error": "human assigner required"}), 403
        multi = get_multi(multi_run_id)
        if not multi:
            return jsonify({"error": "multi run not found"}), 404
        if not authorize(user_id, multi["workspace_id"], "manage_members"):
            return jsonify({"error": "workspace owner required"}), 403
        body = request.get_json(silent=True) or {}
        try:
            value = assign(
                multi_run_id=multi_run_id,
                rag_id=str(body.get("rag_id") or ""),
                reviewer_user_id=str(body.get("reviewer_user_id") or ""),
                assigned_by=user_id,
            )
        except AssignmentError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(value), 201

    @bp.get("/api/rag/multi/<multi_run_id>/finalization")
    def finalization_get(multi_run_id: str):
        value = get_finalization(multi_run_id)
        if not value:
            return jsonify({"finalization": None})
        return jsonify({"finalization": value})

    @bp.post("/api/rag/multi/<multi_run_id>/finalize")
    def multi_finalize(multi_run_id: str):
        user_id = _human()
        if not user_id:
            return jsonify({"error": "human finalizer required"}), 403
        multi = get_multi(multi_run_id)
        if not multi:
            return jsonify({"error": "multi run not found"}), 404
        if not authorize(user_id, multi["workspace_id"], "finalize_review"):
            return jsonify({"error": "finalizer permission required"}), 403
        body = request.get_json(silent=True) or {}
        try:
            value = finalize(
                multi_run_id=multi_run_id,
                decision=str(body.get("decision") or ""),
                note=str(body.get("note") or ""),
                finalized_by=user_id,
            )
        except FinalizationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(value), 201

    return bp
