"""Planned vs actual comparison for experiment runs."""

from __future__ import annotations

import json
from typing import Any


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def compare_planned_actual(planned: dict, actual: dict) -> dict:
    keys = sorted(set(planned) | set(actual))
    deviations = []
    for key in keys:
        in_plan = key in planned
        in_actual = key in actual
        plan_value = planned.get(key)
        actual_value = actual.get(key)
        if not in_actual:
            status = "missing_actual"
        elif not in_plan:
            status = "unplanned"
        elif plan_value == actual_value:
            status = "match"
        else:
            status = "changed"
        delta = None
        pct = None
        if _is_number(plan_value) and _is_number(actual_value):
            delta = actual_value - plan_value
            if plan_value != 0:
                pct = round(delta / plan_value * 100, 2)
        deviations.append(
            {
                "field": key,
                "planned": plan_value,
                "actual": actual_value,
                "status": status,
                "delta": delta,
                "delta_pct": pct,
            }
        )
    summary = {
        "total": len(deviations),
        "match": sum(1 for item in deviations if item["status"] == "match"),
        "changed": sum(1 for item in deviations if item["status"] == "changed"),
        "missing_actual": sum(1 for item in deviations if item["status"] == "missing_actual"),
        "unplanned": sum(1 for item in deviations if item["status"] == "unplanned"),
    }
    summary["compliant"] = summary["changed"] == 0 and summary["missing_actual"] == 0
    return {"summary": summary, "deviations": deviations}


def compare_run_row(row: dict) -> dict:
    planned = json.loads(row.get("planned_json") or "{}")
    actual = json.loads(row.get("actual_json") or "{}")
    return compare_planned_actual(planned, actual)
