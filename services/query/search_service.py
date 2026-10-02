"""
Search Service - V20.3
Handles all database queries for Sci-Pal
"""
import sqlite3
import re
from typing import List, Dict, Any
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
DATABASE_PATH = project_root / "data" / "research.db"


class SearchService:
    """Service for searching across all tables"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DATABASE_PATH)

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_snippet(self, text: str, query: str, context_chars: int = 200) -> str:
        text_lower = text.lower()
        query_lower = query.lower()
        idx = text_lower.find(query_lower)
        if idx == -1:
            return text[:context_chars] + ("..." if len(text) > context_chars else "")
        start = max(0, idx - context_chars // 2)
        end = min(len(text), idx + len(query) + context_chars // 2)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet

    # ============================================================
    # TEXT SEARCH
    # ============================================================
    def text_search(self, query: str, top_k: int = 10, paper_id: str = None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
        SELECT
            p.para_id, p.paper_id, p.section_level1, p.section_level2, p.section_level3,
            p.text, p.sequence, p.page,
            pap.title as paper_title, pap.authors, pap.year, pap.journal
        FROM paragraphs p
        JOIN papers pap ON p.paper_id = pap.paper_id
        WHERE p.text LIKE ?
        """
        params = [f"%{query}%"]

        if paper_id:
            sql += " AND p.paper_id = ?"
            params.append(paper_id)

        sql += " ORDER BY pap.year DESC LIMIT ?"
        params.append(top_k)

        cursor.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]
        for r in results:
            r["snippet"] = self._get_snippet(r["text"], query)

        conn.close()
        return results

    # ============================================================
    # FIGURE SEARCH
    # ============================================================
    def figure_search(self, query: str, top_k: int = 10, paper_id: str = None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
        SELECT
            f.fig_id, f.paper_id, f.fig_number, f.caption, f.file_path, f.page,
            pap.title as paper_title, pap.authors, pap.year
        FROM figures f
        JOIN papers pap ON f.paper_id = pap.paper_id
        WHERE f.caption LIKE ?
        """
        params = [f"%{query}%"]

        if paper_id:
            sql += " AND f.paper_id = ?"
            params.append(paper_id)

        sql += " ORDER BY pap.year DESC LIMIT ?"
        params.append(top_k)

        cursor.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return results

    # ============================================================
    # CITATION SEARCH
    # ============================================================
    def citation_search(self, query: str, top_k: int = 10, paper_id: str = None) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
        SELECT
            c.citation_id, c.paper_id, c.ref_number, c.raw_text,
            c.authors, c.title, c.journal, c.year, c.doi,
            pap.title as paper_title
        FROM citations c
        JOIN papers pap ON c.paper_id = pap.paper_id
        WHERE
            c.authors LIKE ? OR
            c.title LIKE ? OR
            c.journal LIKE ? OR
            c.raw_text LIKE ?
        """
        params = [f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"]

        if paper_id:
            sql += " AND c.paper_id = ?"
            params.append(paper_id)

        sql += " ORDER BY c.year DESC LIMIT ?"
        params.append(top_k)

        cursor.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return results

    # ============================================================
    # PAPER SEARCH
    # ============================================================
    def paper_search(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
        SELECT
            p.paper_id, p.title, p.authors, p.journal, p.year, p.doi,
            p.total_paragraphs, p.total_figures, p.total_citations
        FROM papers p
        WHERE
            p.title LIKE ? OR
            p.authors LIKE ? OR
            p.journal LIKE ?
        ORDER BY p.year DESC
        LIMIT ?
        """
        params = [f"%{query}%", f"%{query}%", f"%{query}%", top_k]

        cursor.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return results

    # ============================================================
    # GET PAPER DETAILS
    # ============================================================
    def get_paper_details(self, paper_id: str) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
        paper = cursor.fetchone()
        if not paper:
            conn.close()
            return None

        paper_dict = dict(paper)

        cursor.execute("""
            SELECT * FROM paragraphs
            WHERE paper_id = ?
            ORDER BY sequence
        """, (paper_id,))
        paper_dict["paragraphs"] = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM figures
            WHERE paper_id = ?
            ORDER BY page, fig_number
        """, (paper_id,))
        paper_dict["figures"] = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT * FROM citations
            WHERE paper_id = ?
            ORDER BY CAST(ref_number AS INTEGER)
        """, (paper_id,))
        paper_dict["citations"] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return paper_dict

    # ============================================================
    # UNIFIED SEARCH (for RAG)
    # ============================================================
    def unified_search(self, query: str, top_k: int = 10) -> Dict[str, List[Dict]]:
        return {
            "papers": self.paper_search(query, top_k=top_k),
            "text": self.text_search(query, top_k=top_k),
            "figures": self.figure_search(query, top_k=top_k // 2),
            "citations": self.citation_search(query, top_k=top_k // 2),
        }
