"""Lightweight biomedical domain taxonomy for adaptive alignment."""

from __future__ import annotations

import re
from typing import Dict, Iterable, Tuple

DOMAINS = {
    "hcc_io": {
        "name": "HCC / immuno-oncology",
        "keywords": [
            "hepatocellular", "hcc", "liver cancer", "immune checkpoint",
            "immunotherapy", "pd-1", "pd-l1", "ctla-4", "atezolizumab",
            "nivolumab", "pembrolizumab", "ipilimumab", "rechallenge",
        ],
    },
    "alzheimers": {
        "name": "Alzheimer's / dementia",
        "keywords": [
            "alzheimer", "dementia", "amyloid", "tau", "cognitive decline",
            "mild cognitive impairment", "biomarker",
        ],
    },
    "endocrinology": {
        "name": "Endocrinology / metabolism",
        "keywords": [
            "diabetes", "insulin", "thyroid", "endocrine", "obesity",
            "metabolic", "glucose", "hba1c",
        ],
    },
    "microbiology": {
        "name": "Microbiology / infection",
        "keywords": [
            "microbiome", "microbiota", "bacterial", "infection",
            "antimicrobial", "gut flora", "pathogen",
        ],
    },
    "oncology_other": {
        "name": "Other oncology",
        "keywords": [
            "cancer", "tumor", "tumour", "carcinoma", "chemotherapy",
            "metastasis", "colorectal", "gastric", "lung cancer", "breast cancer",
            "melanoma", "renal cell", "pancreatic",
        ],
    },
}

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _count_keywords(text: str, keywords: Iterable[str]) -> int:
    lowered = (text or "").lower()
    return sum(lowered.count(keyword.lower()) for keyword in keywords)


def classify_text(title: str = "", abstract: str = "", keywords: str = "") -> Tuple[str, float, Dict[str, float]]:
    text = " ".join((title or "", abstract or "", keywords or ""))
    scores = {
        domain_id: float(_count_keywords(text, config["keywords"]))
        for domain_id, config in DOMAINS.items()
    }
    total = sum(scores.values())
    if total <= 0:
        return "general", 0.0, {"general": 1.0}
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    domain_id, score = ordered[0]
    return domain_id, round(score / total, 4), {key: round(value / total, 4) for key, value in ordered if value}


def classify_query(question: str) -> Dict[str, float]:
    domain_id, confidence, distribution = classify_text(title=question)
    if domain_id == "general":
        return {"general": 1.0}
    return distribution
