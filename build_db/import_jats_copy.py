"""COPY-level JATS XML importer for the independent rebuild database."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from build_db.jats_parser import parse_file
from build_db.sentence_geometry import split_sentences


def _paper_id(pg, filename: str) -> str:
    row = pg.execute("SELECT paper_id FROM papers WHERE filename=%s LIMIT 1", (filename,)).fetchone()
    if row:
        return row["paper_id"]
    return "paper_" + Path(filename).stem.replace(".", "_")


def _year(value):
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


class CopyImporter:
    def __init__(self, pg, batch_size: int = 200) -> None:
        self.pg = pg
        self.batch_size = max(1, batch_size)
        self.rows: Dict[str, List[tuple]] = {
            "papers": [], "sections": [], "figures": [], "tables": [],
            "citations": [], "paragraphs": [], "sentences": [], "sentence_links": [],
        }
        self.papers = 0
        self.stats = {"papers": 0, "sections": 0, "paragraphs": 0, "sentences": 0, "links": 0, "skipped": 0}

    def add(self, xml_path: Path) -> None:
        if self.pg.execute("SELECT 1 FROM papers WHERE filename=%s LIMIT 1", (xml_path.name,)).fetchone():
            self.stats["skipped"] += 1
            return
        data = parse_file(xml_path)
        meta = data.get("metadata") or {}
        paragraphs = data.get("paragraphs") or []
        citations = data.get("references") or []
        figures = data.get("figures") or []
        tables = data.get("tables") or []
        sections = data.get("sections") or []
        paper_id = "paper_" + xml_path.stem.replace(".", "_")

        self.rows["papers"].append(
            (
                paper_id, xml_path.name, meta.get("title") or xml_path.stem,
                "; ".join(meta.get("authors") or []), meta.get("abstract") or "",
                meta.get("journal") or "", _year(meta.get("year")), meta.get("doi") or "",
                ", ".join(meta.get("keywords") or []), None, None, None, "J", None,
                "en", None, None, "completed", "xml", len(paragraphs), len(figures),
                len(tables), len(citations),
            )
        )
        self.stats["papers"] += 1
        self.papers += 1

        section_map: Dict[str, str] = {}
        for index, section in enumerate(sections, 1):
            section_id = f"{paper_id}_sec_{index:04d}"
            section_map[section["section_id"]] = section_id
            self.rows["sections"].append(
                (section_id, paper_id, section_map.get(section.get("parent_id") or ""),
                 section["level"], section["title"], index, None, None, "jats")
            )
            self.stats["sections"] += 1

        fig_map: Dict[str, str] = {}
        for index, fig in enumerate(figures, 1):
            fig_id = f"fig_{paper_id}_{index:04d}"
            if fig.get("id"):
                fig_map[fig["id"]] = fig_id
            self.rows["figures"].append((fig_id, paper_id, fig.get("label"), fig.get("caption"), None))

        table_map: Dict[str, str] = {}
        for index, table in enumerate(tables, 1):
            table_id = f"tbl_{paper_id}_{index:04d}"
            if table.get("id"):
                table_map[table["id"]] = table_id
            self.rows["tables"].append((table_id, paper_id, table.get("label"), table.get("caption"), table.get("markdown")))

        citation_map: Dict[str, str] = {}
        for index, ref in enumerate(citations, 1):
            citation_id = f"cite_{paper_id}_{index:04d}"
            if ref.get("id"):
                citation_map[ref["id"]] = citation_id
            self.rows["citations"].append(
                (citation_id, paper_id, ref.get("id") or str(index), ref.get("text") or "",
                 ref.get("doi"), ref.get("title") or "", None, None, str(_year(ref.get("year")) or ""))
            )

        for index, para in enumerate(paragraphs):
            para_id = f"{paper_id}_para_{index:05d}"
            section_id = section_map.get(para.get("section_id") or "")
            path = para.get("path") or []
            self.rows["paragraphs"].append(
                (para_id, paper_id, path[0] if len(path) > 0 else None,
                 path[1] if len(path) > 1 else None, path[2] if len(path) > 2 else None,
                 para["text"], para["sequence"], None, None, section_id,
                 json.dumps(path, ensure_ascii=False) if path else None)
            )
            self.stats["paragraphs"] += 1
            sentences = split_sentences(para["text"])
            offsets = []
            cursor = 0
            for sentence in sentences:
                start = para["text"].find(sentence, cursor)
                if start < 0:
                    start = cursor
                offsets.append((start, start + len(sentence)))
                cursor = start + len(sentence)
            for sindex, sentence in enumerate(sentences, 1):
                sentence_id = f"{para_id}_sent_{sindex:03d}"
                self.rows["sentences"].append(
                    (sentence_id, para_id, paper_id, sentence, sindex, None, None,
                     section_id, offsets[sindex - 1][0], offsets[sindex - 1][1])
                )
                self.stats["sentences"] += 1
            linked = set()
            for xref in para.get("xrefs") or []:
                offset = xref.get("offset", 0)
                sentence_index = None
                for sindex, (start, end) in enumerate(offsets):
                    if start <= offset <= end:
                        sentence_index = sindex + 1
                        break
                if sentence_index is None:
                    continue
                sentence_id = f"{para_id}_sent_{sentence_index:03d}"
                rid = xref.get("rid") or ""
                ref_type = (xref.get("ref_type") or "").lower()
                if ref_type == "bibr" and rid in citation_map:
                    target_type, target_id = "citation", citation_map[rid]
                elif ref_type == "fig" and rid in fig_map:
                    target_type, target_id = "figure", fig_map[rid]
                elif ref_type == "table" and rid in table_map:
                    target_type, target_id = "table", table_map[rid]
                else:
                    continue
                key = (sentence_id, target_type, target_id)
                if key in linked:
                    continue
                linked.add(key)
                self.rows["sentence_links"].append(
                    (f"jats_{sentence_id}_{target_type}_{target_id}", sentence_id, para_id, paper_id,
                     "sentence", target_type, target_id, "mentions", None, None, "jats-regex", 0.6)
                )
                self.stats["links"] += 1

        if self.papers >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.rows["papers"]:
            return
        copy_specs = [
            ("papers", "paper_id,filename,title,authors,abstract,journal,year,doi,keywords,volume,issue,pages,paper_type,publisher,language,affiliations,funding,parse_status,parse_engine,total_paragraphs,total_figures,total_tables,total_citations"),
            ("sections", "section_id,paper_id,parent_id,level,title,seq,page,bbox,source"),
            ("figures", "fig_id,paper_id,fig_number,caption,file_path"),
            ("tables", "table_id,paper_id,table_number,caption,markdown"),
            ("citations", "citation_id,paper_id,ref_number,raw_text,doi,title,authors,journal,year"),
            ("paragraphs", "para_id,paper_id,section_level1,section_level2,section_level3,text,sequence,page,bbox,section_id,section_path"),
            ("sentences", "sentence_id,para_id,paper_id,text,sequence,page,bbox,section_id,char_start,char_end"),
            ("sentence_links", "link_id,sentence_id,para_id,paper_id,source_type,target_type,target_id,relation,page,bbox,source,confidence"),
        ]
        try:
            for table, columns in copy_specs:
                rows = self.rows[table]
                if not rows:
                    continue
                with self.pg.cursor() as cur:
                    with cur.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
                        for row in rows:
                            copy.write_row(row)
            self.pg.commit()
        except Exception:
            self.pg.rollback()
            raise
        self.rows = {key: [] for key in self.rows}
        self.papers = 0

    def close(self) -> None:
        self.flush()
