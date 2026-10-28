"""Data classification, profiling, aggregation and redaction policy."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

MIN_AGG_N = int(os.environ.get("SCIPAL_MIN_AGG_N", "10"))
MAX_SAMPLE_ROWS = int(os.environ.get("SCIPAL_MAX_SAMPLE_ROWS", "5"))

SENSITIVE = re.compile(
    r"(name|姓|名|id|身份证|phone|tel|mobile|手机|email|邮箱|address|地址|"
    r"dob|birth|生日|出生|patient|病人|ssn|passport|护照)",
    re.IGNORECASE,
)
CLOUD_PROVIDERS = [
    item.strip().lower()
    for item in os.environ.get("SCIPAL_CLOUD_PROVIDERS", "deepseek,openai").split(",")
    if item.strip()
]
RAW_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".docx", ".doc"}
PUBLIC_SUFFIXES = {".pdf", ".xml", ".json", ".md", ".txt"}


def classify(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in RAW_SUFFIXES:
        return "raw"
    if suffix in PUBLIC_SUFFIXES:
        return "public"
    return "raw"


def session_policy(data_class: str) -> Dict[str, Any]:
    if data_class == "raw":
        return {
            "models": ["local"],
            "tools": ["data_inspect", "data_profile", "data_query", "data_sample", "data_export"],
            "cloud": False,
        }
    if data_class == "public":
        return {
            "models": ["local", "cloud"],
            "tools": ["search_evidence", "get_context", "verify_answer", "watch_run"],
            "cloud": True,
        }
    return {
        "models": ["local"],
        "tools": ["artifact_list", "artifact_read", "artifact_validate"],
        "cloud": False,
    }


def provider_allowed(provider: str) -> bool:
    return str(provider or "").strip().lower() in CLOUD_PROVIDERS


def is_sensitive_column(name: str) -> bool:
    return bool(SENSITIVE.search(str(name)))


def load_table(path: str | Path, sheet: Optional[str] = None) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=sep)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0)
    if suffix in (".docx", ".doc"):
        from docx import Document

        text = "\n".join(p.text for p in Document(str(path)).paragraphs if p.text.strip())
        return pd.DataFrame({"text": [text]})
    raise ValueError(f"unsupported data file: {suffix}")


def _suppressed(value: Any, count: int, threshold: int) -> Any:
    if count < threshold:
        return f"<{threshold}"
    return value


def profile_frame(df: pd.DataFrame, top_k: int = 5) -> Dict[str, Any]:
    columns = []
    for name in df.columns:
        series = df[name]
        entry: Dict[str, Any] = {
            "name": str(name),
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "unique": int(series.nunique(dropna=True)),
            "sensitive": is_sensitive_column(str(name)),
        }
        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            entry.update(
                {
                    "min": float(clean.min()) if len(clean) else None,
                    "max": float(clean.max()) if len(clean) else None,
                    "mean": float(clean.mean()) if len(clean) else None,
                }
            )
        else:
            counts = series.dropna().astype(str).value_counts().head(top_k)
            entry["top_values"] = [
                {"value": _suppressed(value, int(count), MIN_AGG_N), "n": int(count)}
                for value, count in counts.items()
            ]
        columns.append(entry)
    return {"rows": int(len(df)), "columns": columns, "min_agg_n": MIN_AGG_N}


def aggregate_frame(
    df: pd.DataFrame,
    group_by: Iterable[str],
    metrics: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Group-by with small-cell suppression (n < MIN_AGG_N)."""
    keys = [key for key in group_by if key in df.columns]
    if not keys:
        raise ValueError("group_by columns not found")
    grouped = df.groupby(keys, dropna=False).size().reset_index(name="n")
    value_cols = [m for m in (metrics or []) if m in df.columns]
    if value_cols:
        means = df.groupby(keys, dropna=False)[value_cols].mean().reset_index()
        grouped = grouped.merge(means, on=keys, how="left")
    grouped["n"] = grouped["n"].apply(lambda value: value if value >= MIN_AGG_N else None)
    grouped = grouped[grouped["n"].notna()].reset_index(drop=True)
    return grouped


def sample_frame(df: pd.DataFrame, columns: Optional[List[str]] = None) -> pd.DataFrame:
    """At most MAX_SAMPLE_ROWS rows, sensitive columns dropped."""
    allowed = [
        column
        for column in (columns or list(df.columns))
        if column in df.columns and not is_sensitive_column(str(column))
    ]
    if not allowed:
        return pd.DataFrame()
    return df[allowed].head(MAX_SAMPLE_ROWS).copy()


def redact_text(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", text or "")
    text = re.sub(r"\b1[3-9]\d{9}\b", "<phone>", text)
    text = re.sub(r"\b\d{17}[\dXx]\b", "<id>", text)
    return text
