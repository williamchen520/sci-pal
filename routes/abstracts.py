"""Abstracts library read-only routes (``data/abstracts.db``)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Blueprint, jsonify, request


def build_abstracts_blueprint(*, db_path: Path) -> Blueprint:
    bp = Blueprint("abstracts", __name__, url_prefix="/api")
    abstract_db = Path(db_path)

    @bp.get("/abstracts/list")
    def list_abstracts():
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 20, type=int)
        search = request.args.get("search", "", type=str)

        if not abstract_db.exists():
            return jsonify({"error": "摘要数据库不存在"}), 404

        conn = sqlite3.connect(str(abstract_db))
        conn.row_factory = sqlite3.Row
        try:
            if search:
                count_row = conn.execute(
                    "SELECT COUNT(*) as total FROM papers WHERE title LIKE ? OR abstract LIKE ?",
                    (f"%{search}%", f"%{search}%"),
                ).fetchone()
            else:
                count_row = conn.execute("SELECT COUNT(*) as total FROM papers").fetchone()
            total = count_row["total"]

            offset = (page - 1) * page_size
            if search:
                rows = conn.execute(
                    "SELECT pmid, doi, title, authors, journal, year, topic FROM papers "
                    "WHERE title LIKE ? OR abstract LIKE ? ORDER BY year DESC LIMIT ? OFFSET ?",
                    (f"%{search}%", f"%{search}%", page_size, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT pmid, doi, title, authors, journal, year, topic FROM papers "
                    "ORDER BY year DESC LIMIT ? OFFSET ?",
                    (page_size, offset),
                ).fetchall()
        finally:
            conn.close()

        papers = [
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

    @bp.get("/abstracts/<paper_id>")
    def get_abstract(paper_id: str):
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
