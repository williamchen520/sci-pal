"""Abstracts library routes (PostgreSQL only)."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request


def _pg():
    from services.db.pg_pool import corpus_connection

    return corpus_connection()


def build_abstracts_blueprint(*, db_path: Path | None = None) -> Blueprint:
    bp = Blueprint("abstracts", __name__, url_prefix="/api")

    @bp.get("/abstracts/list")
    def list_abstracts():
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 20, type=int)
        search = request.args.get("search", "", type=str)
        offset = (page - 1) * page_size

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

    @bp.get("/abstracts/<paper_id>")
    def get_abstract(paper_id: str):
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

    return bp
