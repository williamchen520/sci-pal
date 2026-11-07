"""Abstracts library routes: PostgreSQL primary, SQLite legacy fallback."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify, request


def _pg_enabled() -> bool:
    return os.environ.get("SCIPAL_ABSTRACTS_BACKEND", "").strip().lower() in {
        "postgres", "postgresql", "pg", "1", "true"
    }


def _pg():
    from services.db.pg_pool import pg_connection

    return pg_connection()


def build_abstracts_blueprint(*, db_path: Path) -> Blueprint:
    bp = Blueprint("abstracts", __name__, url_prefix="/api")
    abstract_db = Path(db_path)

    @bp.get("/abstracts/list")
    def list_abstracts():
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 20, type=int)
        search = request.args.get("search", "", type=str)
        offset = (page - 1) * page_size

        if _pg_enabled():
            pg = _pg()
            try:
                where = ""
                params: list[object] = []
                if search:
                    where = "WHERE title ILIKE %s OR abstract ILIKE %s"
                    params = [f"%{search}%", f"%{search}%"]
                total = pg.execute(
                    f"SELECT COUNT(*) AS total FROM abstracts {where}", params
                ).fetchone()["total"]
                rows = pg.execute(
                    "SELECT pmid,doi,title,authors,journal,year,topic,source "
                    f"FROM abstracts {where} ORDER BY year DESC LIMIT %s OFFSET %s",
                    [*params, page_size, offset],
                ).fetchall()
            finally:
                pg.close()
            papers = [
                {
                    "paper_id": str(row["pmid"] or ""),
                    "title": row["title"],
                    "authors": row["authors"],
                    "journal": row["journal"],
                    "year": row["year"],
                    "topic": row["topic"],
                    "source": row["source"] or "abstract",
                }
                for row in rows
            ]
            return jsonify(
                {
                    "papers": papers,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size,
                }
            )

        if not abstract_db.exists():
            return jsonify({"error": "摘要数据库不存在"}), 404

        conn = sqlite3.connect(str(abstract_db))
        conn.row_factory = sqlite3.Row
        try:
            if search:
                where = "WHERE title LIKE ? OR abstract LIKE ?"
                params = (f"%{search}%", f"%{search}%")
            else:
                where = ""
                params = ()
            total = conn.execute(
                f"SELECT COUNT(*) AS total FROM papers {where}", params
            ).fetchone()["total"]
            rows = conn.execute(
                "SELECT pmid, doi, title, authors, journal, year, topic FROM papers "
                f"{where} ORDER BY year DESC LIMIT ? OFFSET ?",
                (*params, page_size, offset),
            ).fetchall()
        finally:
            conn.close()

        return jsonify(
            {
                "papers": [
                    {
                        "paper_id": str(row["pmid"]),
                        "title": row["title"],
                        "authors": row["authors"],
                        "journal": row["journal"],
                        "year": row["year"],
                        "topic": row["topic"],
                        "source": "abstract",
                    }
                    for row in rows
                ],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        )

    @bp.get("/abstracts/<paper_id>")
    def get_abstract(paper_id: str):
        if _pg_enabled():
            pg = _pg()
            try:
                row = pg.execute(
                    "SELECT pmid,doi,title,abstract,authors,journal,year,topic "
                    "FROM abstracts WHERE pmid=%s",
                    (paper_id,),
                ).fetchone()
            finally:
                pg.close()
            if not row:
                return jsonify({"error": "摘要未找到"}), 404
            return jsonify(
                {
                    "pmid": row["pmid"],
                    "doi": row["doi"],
                    "title": row["title"],
                    "abstract": row["abstract"],
                    "authors": row["authors"],
                    "journal": row["journal"],
                    "year": row["year"],
                    "topic": row["topic"],
                }
            )

        if not abstract_db.exists():
            return jsonify({"error": "摘要数据库不存在"}), 404

        conn = sqlite3.connect(str(abstract_db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT pmid, doi, title, abstract, authors, journal, year, topic "
                "FROM papers WHERE pmid = ?",
                (paper_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"error": "摘要未找到"}), 404

        return jsonify(
            {
                "pmid": row["pmid"],
                "doi": row["doi"],
                "title": row["title"],
                "abstract": row["abstract"],
                "authors": row["authors"],
                "journal": row["journal"],
                "year": row["year"],
                "topic": row["topic"],
            }
        )

    return bp
