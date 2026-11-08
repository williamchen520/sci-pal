"""Load the P3b PMC OA benchmark corpus into library_bench."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_db.jats_parser import parse_file
from build_db.sentence_geometry import split_sentences
from services.db.pg_pool import pg_connection

MANIFEST = Path(r"D:/sciPal/eval/bench/p3b_manifest.json")


def _doi(value: str) -> str:
    text = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def _work_id(doi: str, pmcid: str) -> str:
    identity = f"doi:{doi}" if doi else f"pmcid:{pmcid}"
    return "work_" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_one(pg, item) -> dict:
    pmcid = item["pmcid"]
    path = Path(item["path"])
    data = parse_file(path)
    meta = data.get("metadata") or {}
    doi = _doi(meta.get("doi") or item.get("doi") or "")
    work_id = _work_id(doi, pmcid)
    sha = _sha(path)
    document_id = f"doc_{sha[:16]}_xml_{work_id[-8:]}"

    pg.execute(
        "INSERT INTO catalog.works (work_id, primary_doi, pmcid, title, year) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (work_id) DO UPDATE SET "
        "primary_doi=EXCLUDED.primary_doi, pmcid=EXCLUDED.pmcid, title=EXCLUDED.title, year=EXCLUDED.year",
        (work_id, doi or None, pmcid, meta.get("title"), meta.get("year")),
    )
    pg.execute(
        "INSERT INTO library_bench.documents "
        "(document_id, work_id, library_id, source_type, source_path, sha256, parser, parser_version) "
        "VALUES (%s,%s,'library_bench','xml',%s,%s,'jats',%s)",
        (document_id, work_id, str(path), sha, "p3b"),
    )

    root_node = f"{document_id}_root"
    pg.execute(
        "INSERT INTO library_bench.source_nodes (node_id,document_id,parent_node_id,node_type,source_path,source_order,native_json) "
        "VALUES (%s,%s,NULL,'document','/article',0,%s::jsonb)",
        (root_node, document_id, json.dumps({"pmcid": pmcid})),
    )

    sections = data.get("sections") or []
    section_ids = {}
    for idx, sec in enumerate(sections, 1):
        raw = sec.get("section_id") or f"sec_{idx:04d}"
        sid = f"{document_id}_{raw}"
        parent_raw = sec.get("parent_id")
        pid = f"{document_id}_{parent_raw}" if parent_raw else None
        node_id = f"{document_id}_node_{raw}"
        section_ids[raw] = sid
        title = sec.get("title") or ""
        path_text = " > ".join(sec.get("path") or [])
        pg.execute(
            "INSERT INTO library_bench.source_nodes (node_id,document_id,parent_node_id,node_type,source_path,source_order,native_json) "
            "VALUES (%s,%s,%s,'section',%s,%s,%s::jsonb)",
            (node_id, document_id, root_node, sec.get("xpath") or "", idx, json.dumps({"title": title, "path": sec.get("path") or []})),
        )
        pg.execute(
            "INSERT INTO library_bench.sections (section_id,document_id,parent_id,level,seq,title,path,depth,source_node_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (sid, document_id, pid, sec.get("level"), idx, title, path_text, sec.get("level"), node_id),
        )

    paragraphs = data.get("paragraphs") or []
    for idx, para in enumerate(paragraphs):
        pid = f"{document_id}_p{idx:04d}"
        raw_sec = para.get("section_id")
        sid = section_ids.get(raw_sec) if raw_sec else None
        node_id = f"{document_id}_node_p{idx:04d}"
        parent = f"{document_id}_node_{raw_sec}" if raw_sec else root_node
        text = para.get("text") or ""
        pg.execute(
            "INSERT INTO library_bench.source_nodes (node_id,document_id,parent_node_id,node_type,source_path,source_order,native_json) "
            "VALUES (%s,%s,%s,'paragraph',%s,%s,%s::jsonb)",
            (node_id, document_id, parent, para.get("xpath") or "", idx, json.dumps({"path": para.get("path") or []})),
        )
        pg.execute(
            "INSERT INTO library_bench.paragraphs (para_id,document_id,section_id,seq,text,source_node_id) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (pid, document_id, sid, idx, text, node_id),
        )
        offset = 0
        for sent_idx, sentence in enumerate(split_sentences(text)):
            sent_id = f"{pid}_s{sent_idx:03d}"
            start = text.find(sentence, offset)
            if start < 0:
                start = offset
            end = start + len(sentence)
            offset = end
            pg.execute(
                "INSERT INTO library_bench.sentences "
                "(sentence_id,document_id,para_id,section_id,seq,text,char_start,char_end,source_node_id,search_vector) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,to_tsvector('english',%s))",
                (sent_id, document_id, pid, sid, sent_idx, sentence, start, end, node_id, sentence),
            )
    return {"document_id": document_id, "sections": len(sections), "paragraphs": len(paragraphs)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))["items"]
    if args.limit:
        items = items[: args.limit]
    print(f"items={len(items)} apply={args.apply}")
    if not args.apply:
        for item in items[:3]:
            print(item["pmcid"], item["title"][:80])
        return 0

    pg = pg_connection()
    try:
        pg.execute(
            "TRUNCATE library_bench.sentences, library_bench.paragraphs, "
            "library_bench.sections, library_bench.source_nodes, library_bench.documents CASCADE"
        )
        total = {"sections": 0, "paragraphs": 0}
        for index, item in enumerate(items, 1):
            stats = load_one(pg, item)
            total["sections"] += stats["sections"]
            total["paragraphs"] += stats["paragraphs"]
            if index % 5 == 0:
                print(f"loaded {index}/{len(items)}")
        pg.commit()
        print("loaded", len(items), total)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
