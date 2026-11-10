"""Backfill abstract-only papers in the rebuild database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_db.sentence_geometry import split_sentences  # noqa: E402
from services.db.pg_pool import pg_connection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=500)
    args = parser.parse_args()
    pg = pg_connection()
    total = 0
    try:
        rows = pg.execute(
            "SELECT paper_id, abstract FROM papers p WHERE NOT EXISTS "
            "(SELECT 1 FROM paragraphs pa WHERE pa.paper_id=p.paper_id) "
            "AND coalesce(trim(abstract),'') <> ''"
        ).fetchall()
        for row in rows:
            paper_id = row["paper_id"]
            text = row["abstract"].strip()
            section_id = f"{paper_id}_sec_abstract"
            para_id = f"{paper_id}_para_abstract"
            pg.execute(
                "INSERT INTO sections (section_id,paper_id,parent_id,level,title,seq,source,depth,path) "
                "VALUES (%s,%s,NULL,1,'Abstract',1,'jats-abstract',1,'Abstract') "
                "ON CONFLICT (section_id) DO NOTHING",
                (section_id, paper_id),
            )
            pg.execute(
                "INSERT INTO paragraphs (para_id,paper_id,section_level1,text,sequence,section_id,section_path) "
                "VALUES (%s,%s,'Abstract',%s,1,%s,%s) ON CONFLICT (para_id) DO NOTHING",
                (para_id, paper_id, text, section_id, json.dumps(["Abstract"])),
            )
            sentences = split_sentences(text)
            cursor = 0
            for index, sentence in enumerate(sentences, 1):
                start = text.find(sentence, cursor)
                if start < 0:
                    start = cursor
                cursor = start + len(sentence)
                pg.execute(
                    "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence,section_id,char_start,char_end) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (sentence_id) DO NOTHING",
                    (f"{para_id}_sent_{index:03d}", para_id, paper_id, sentence, index, section_id, start, cursor),
                )
            total += 1
            if total % args.batch == 0:
                pg.commit()
                print("backfilled", total, flush=True)
        pg.commit()
    finally:
        pg.close()
    print("total", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
