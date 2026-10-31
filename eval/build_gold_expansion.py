"""Build additional silver questions from existing sentences.

The first 30 gold questions are curated; this script appends questions generated
from real sentences (optionally with a local LLM) so the retrieval benchmark can
reach 100 quickly. Auto entries are marked ``source=auto`` and should be
spot-checked.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.request
from pathlib import Path
from typing import Dict, List

DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
GOLD = Path(__file__).resolve().parent / "gold" / "seed.jsonl"
OUT = Path(__file__).resolve().parent / "gold" / "seed_auto.jsonl"

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9-]{4,}")
STOP = {
    "these", "those", "their", "there", "which", "while", "using", "study",
    "patients", "results", "review", "however", "therefore", "between",
    "associated", "significant", "clinical", "treatment", "disease", "paper",
    "characterized", "increased", "reduced", "observed", "showed", "reported",
    "including", "resulting", "respectively", "significantly", "important",
    "potential", "current", "different", "various", "compared", "treated",
    "found", "based", "related", "higher", "lower", "levels", "groups",
}
TEMPLATES = [
    "What does the paper report about {a} and {b}?",
    "How does the study describe the relationship between {a} and {b}?",
    "What role does {a} play according to the paper?",
    "What evidence is provided about {a} in this paper?",
]


def _keys(text: str) -> List[str]:
    seen = []
    for token in TOKEN.findall(text):
        lowered = token.lower()
        if lowered in STOP or lowered in seen:
            continue
        seen.append(lowered)
        if len(seen) == 3:
            break
    return seen


def _llm_question(
    model: str, title: str, sentence: str, host: str = "http://127.0.0.1:11434"
) -> str:
    prompt = (
        "Write ONE specific research question that the following sentence answers. "
        "Use the paper title for context. Return only the question, ending with '?'.\n"
        f"Title: {title}\nSentence: {sentence}\nQuestion:"
    )
    payload = json.dumps(
        {
            "model": model,
            "stream": False,
            "options": {"temperature": 0.2},
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            text = json.loads(response.read()).get("message", {}).get("content", "")
    except Exception:  # noqa: BLE001
        return ""
    line = (text or "").strip().splitlines()[0].strip().strip('"')
    if line.endswith("?") and 15 <= len(line) <= 180:
        return line
    return ""


def _candidates(conn: sqlite3.Connection, used_papers: set, limit: int) -> List[Dict]:
    rows = conn.execute(
        "SELECT p.paper_id, p.title, COUNT(s.sentence_id) AS n "
        "FROM papers p JOIN sentences s ON s.paper_id = p.paper_id "
        "WHERE p.title IS NOT NULL AND length(p.title) > 20 "
        "AND p.title NOT LIKE '%Abstract%' AND p.title NOT LIKE '%Correction%' "
        "GROUP BY p.paper_id HAVING n BETWEEN 25 AND 400 "
        "ORDER BY n DESC LIMIT 80"
    ).fetchall()
    out = []
    for paper_id, title, _ in rows:
        if paper_id in used_papers:
            continue
        sentences = conn.execute(
            "SELECT sentence_id, para_id, text FROM sentences "
            "WHERE paper_id = ? AND length(text) BETWEEN 120 AND 340 "
            "AND text NOT LIKE 'Figure%' AND text NOT LIKE 'Table%' "
            "AND text NOT LIKE '%et al%' ORDER BY rowid LIMIT 40",
            (paper_id,),
        ).fetchall()
        seen_paras = set()
        picked = []
        for sentence_id, para_id, text in sentences:
            if para_id in seen_paras:
                continue
            keys = _keys(text)
            if len(keys) < 2:
                continue
            seen_paras.add(para_id)
            picked.append((sentence_id, text, keys))
            if len(picked) == 3:
                break
        if len(picked) == 3:
            out.append({"paper_id": paper_id, "title": title, "picked": picked})
        if len(out) >= limit:
            break
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=70)
    parser.add_argument("--model", default="", help="Ollama model; empty = template only")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    gold = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    used_papers = {item["paper_ids"][0] for item in gold if item.get("paper_ids")}
    existing = {item["evidence"][0] for item in gold if item.get("evidence")}
    questions_seen = {item["question"].lower() for item in gold}

    conn = sqlite3.connect(DB)
    papers = _candidates(conn, used_papers, max(1, args.count // 3))
    conn.close()

    entries = []
    index = len(gold)
    for paper in papers:
        for offset, (sentence_id, text, keys) in enumerate(paper["picked"]):
            if sentence_id in existing:
                continue
            template = TEMPLATES[(index + offset) % len(TEMPLATES)]
            fallback = template.format(a=keys[0], b=keys[1] if len(keys) > 1 else keys[0])
            question = fallback
            if args.model:
                generated = _llm_question(args.model, paper["title"], text)
                if generated and generated.lower() not in questions_seen:
                    question = generated
            if question.lower() in questions_seen:
                continue
            questions_seen.add(question.lower())
            index += 1
            entries.append(
                {
                    "id": f"q{index:03d}",
                    "question": question,
                    "paper_ids": [paper["paper_id"]],
                    "evidence": [sentence_id],
                    "answer_points": keys,
                    "category": "auto",
                    "difficulty": "medium",
                    "forbidden": [],
                    "source": "auto",
                    "paper_title": paper["title"][:120],
                }
            )
            if len(entries) >= args.count:
                break
        if len(entries) >= args.count:
            break

    out = Path(args.out)
    out.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} to {out}")


if __name__ == "__main__":
    main()
