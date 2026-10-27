"""
Database Writer
Inserts parsed PDF results into our SQLite database
Follows our "physical single file, logical multi-table" architecture
"""
import sqlite3
import os
import json
from typing import Dict, List, Any
from config.settings import DATABASE_PATH

class DatabaseWriter:
    """Writes parsed paper data into the database"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DATABASE_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # V25.18: 缓存 papers 表实际字段，避免插入不存在的列报错
        self.paper_columns = self._get_table_columns('papers')

    def _get_table_columns(self, table_name: str) -> set:
        """获取表的实际字段集合"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = {row[1] for row in cursor.fetchall()}
            conn.close()
            return columns
        except Exception:
            return set()
    
    def _get_connection(self):
        """Get a new database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    
    def insert_paper(self, parsed_result: Dict[str, Any]) -> bool:
        """
        Insert a complete parsed paper into the database
        
        Args:
            parsed_result: Output from parser orchestrator
            
        Returns:
            True if successful
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            paper_id = parsed_result["paper_id"]
            metadata = parsed_result.get("metadata", {})
            
            # 计算各类型数量（用于 papers 表的统计列）
            paragraphs = parsed_result.get("paragraphs", [])
            figures = parsed_result.get("figures", [])
            citations = parsed_result.get("citations", [])
            tables = parsed_result.get("tables", [])
            
            print(f"💾 Inserting paper {paper_id} into database...")
            
            # Insert paper metadata（V25.14修复: 匹配 build_database.py 的实际 schema）
            self._insert_paper_metadata(cursor, paper_id, metadata, {
                "total_paragraphs": len(paragraphs),
                "total_figures": len(figures),
                "total_tables": len(tables),
                "total_citations": len(citations),
            })
            self._write_provenance(cursor, paper_id, parsed_result.get("provenance"))
            
            # Insert paragraphs
            self._insert_paragraphs(cursor, paragraphs)
            print(f"  ✅ Inserted {len(paragraphs)} paragraphs")
            
            # Insert figures
            self._insert_figures(cursor, figures)
            print(f"  ✅ Inserted {len(figures)} figures")
            
            # Insert citations
            self._insert_citations(cursor, citations)
            self._insert_citation_mentions(
                cursor, paper_id, parsed_result.get("intext_citations") or []
            )
            print(f"  ✅ Inserted {len(citations)} citations")
            
            # Insert tables
            self._insert_tables(cursor, tables)
            print(f"  ✅ Inserted {len(tables)} tables")
            
            conn.commit()
            print(f"✅ Paper {paper_id} inserted successfully!")
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Error inserting paper: {e}")
            return False
        finally:
            conn.close()
    
    def _insert_paper_metadata(self, cursor, paper_id: str, metadata: Dict[str, Any], counts: Dict[str, int]):
        """Insert paper metadata（V25.18修复: 动态检查字段，只插入数据库实际存在的列，避免 no such column 错误）

        支持的字段（存在才插入）: paper_id, filename, title, authors, abstract, journal, year, doi, keywords,
                volume, issue, pages, paper_type, publisher, language, affiliations, funding,
                parse_status, parse_engine, total_paragraphs, total_figures, total_tables, total_citations,
                created_at, updated_at
        """
        filename = metadata.get("file_name") or metadata.get("filename") or os.path.basename(metadata.get("file_path", ""))

        # 构建字段->值的映射
        field_values = {
            'paper_id': paper_id,
            'filename': filename,
            'title': metadata.get("title", "Untitled"),
            'authors': ", ".join(metadata.get("authors", [])) if isinstance(metadata.get("authors"), list) else metadata.get("authors", ""),
            'abstract': metadata.get("abstract", ""),
            'journal': metadata.get("journal", ""),
            'year': metadata.get("year"),
            'doi': metadata.get("doi", ""),
            'keywords': ", ".join(metadata.get("keywords", [])) if isinstance(metadata.get("keywords"), list) else metadata.get("keywords", ""),
            'volume': metadata.get("volume", ""),
            'issue': metadata.get("issue", ""),
            'pages': metadata.get("pages", ""),
            'paper_type': metadata.get("paper_type", "J"),
            'publisher': metadata.get("publisher", ""),
            'language': metadata.get("language", "en"),
            'affiliations': ", ".join(metadata.get("affiliations", [])) if isinstance(metadata.get("affiliations"), list) else metadata.get("affiliations", ""),
            'funding': metadata.get("funding", ""),
            'parse_status': metadata.get("parse_status", "completed"),
            'parse_engine': metadata.get("parse_engine", ""),
            'total_paragraphs': counts.get("total_paragraphs", 0),
            'total_figures': counts.get("total_figures", 0),
            'total_tables': counts.get("total_tables", 0),
            'total_citations': counts.get("total_citations", 0),
        }

        # 只保留数据库里实际存在的字段
        if self.paper_columns:
            valid_fields = {k: v for k, v in field_values.items() if k in self.paper_columns}
        else:
            valid_fields = field_values

        # updated_at 特殊处理（用 CURRENT_TIMESTAMP）
        if 'updated_at' in self.paper_columns or not self.paper_columns:
            valid_fields['updated_at'] = None  # 占位，下面用 CURRENT_TIMESTAMP

        # 动态构建 INSERT 语句
        columns = ', '.join(valid_fields.keys())
        # updated_at 用 CURRENT_TIMESTAMP，其他用 ?
        placeholders = ', '.join(
            'CURRENT_TIMESTAMP' if col == 'updated_at' else '?'
            for col in valid_fields.keys()
        )
        values = [v for k, v in valid_fields.items() if k != 'updated_at']

        query = f"INSERT OR REPLACE INTO papers ({columns}) VALUES ({placeholders})"
        cursor.execute(query, values)
    
    def _write_provenance(self, cursor, paper_id: str, provenance: Dict[str, Any] | None) -> None:
        """Persist per-field engine provenance (text/meta/refs/tables + decision)."""
        if not provenance:
            return
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS parse_provenance (
                paper_id      TEXT PRIMARY KEY,
                text_engine   TEXT,
                meta_engine   TEXT,
                refs_engine   TEXT,
                tables_engine TEXT,
                decision      TEXT,
                metrics_json  TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO parse_provenance
                (paper_id, text_engine, meta_engine, refs_engine, tables_engine,
                 decision, metrics_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                paper_id,
                provenance.get("text_engine", ""),
                provenance.get("meta_engine", ""),
                provenance.get("refs_engine", ""),
                provenance.get("tables_engine", ""),
                provenance.get("decision", ""),
                json.dumps(provenance.get("metrics") or {}, ensure_ascii=False),
            ),
        )

    def _insert_paragraphs(self, cursor, paragraphs: List[Dict[str, Any]]):
        """Insert paragraphs; section_path is stored as JSON when available."""
        existing = self._get_table_columns("paragraphs")
        include_path = "section_path" in existing
        columns = [
            "para_id", "paper_id", "section_level1", "section_level2",
            "section_level3", "text", "sequence", "page", "bbox",
        ]
        if include_path:
            columns.append("section_path")
        placeholders = ", ".join("?" for _ in columns)
        for para in paragraphs:
            values = [
                para.get("para_id"),
                para.get("paper_id"),
                para.get("section_type") or para.get("section_level1"),
                para.get("section_title") or para.get("section_level2"),
                para.get("section_level3"),
                para.get("text_content") or para.get("text"),
                para.get("para_index") or para.get("sequence"),
                para.get("page_number") or para.get("page"),
                str(para.get("bbox", "")) if para.get("bbox") else None,
            ]
            if include_path:
                path = para.get("section_path") or []
                values.append(json.dumps(path, ensure_ascii=False) if path else None)
            cursor.execute(
                f"INSERT OR REPLACE INTO paragraphs ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                values,
            )
    
    def _insert_figures(self, cursor, figures: List[Dict[str, Any]]):
        """Insert figures（V25.14修复: 匹配实际 figures 表 schema）
        
        实际表结构: fig_id, paper_id, fig_number, caption, file_path, page, bbox
        """
        for fig in figures:
            cursor.execute('''
            INSERT OR REPLACE INTO figures 
            (fig_id, paper_id, fig_number, caption, file_path, page, bbox)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                fig.get("figure_id") or fig.get("fig_id"),
                fig.get("paper_id"),
                fig.get("figure_number") or fig.get("fig_number"),
                fig.get("caption"),
                fig.get("image_path") or fig.get("file_path"),
                fig.get("page_number") or fig.get("page"),
                str(fig.get("bbox", "")) if fig.get("bbox") else None,
            ))
    
    def _insert_citations(self, cursor, citations: List[Dict[str, Any]]):
        """Insert citations; page/bbox are stored when the schema has them."""
        columns = [
            "citation_id", "paper_id", "ref_number", "raw_text",
            "doi", "title", "authors", "journal", "year",
        ]
        existing = self._get_table_columns("citations")
        optional = [c for c in ("page", "bbox") if c in existing]
        columns.extend(optional)
        placeholders = ", ".join("?" for _ in columns)
        for cit in citations:
            base = [
                cit.get("citation_id"),
                cit.get("paper_id"),
                cit.get("ref_index") or cit.get("ref_number"),
                cit.get("raw_text"),
                cit.get("doi"),
                cit.get("title"),
                cit.get("author") or cit.get("authors"),
                cit.get("journal"),
                cit.get("year"),
            ]
            values = base + [
                cit.get("page") if col == "page" else cit.get("bbox")
                for col in optional
            ]
            cursor.execute(
                f"INSERT OR REPLACE INTO citations ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                values,
            )

    def _insert_citation_mentions(self, cursor, paper_id: str, mentions: List[Dict[str, Any]]):
        """Persist in-text citation mentions (GROBID page/bbox/context)."""
        if not mentions:
            return
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS citation_mentions (
                mention_id TEXT PRIMARY KEY,
                paper_id   TEXT NOT NULL,
                ref_number TEXT,
                page       INTEGER,
                bbox       TEXT,
                context    TEXT,
                source     TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for index, mention in enumerate(mentions, 1):
            cursor.execute(
                "INSERT OR REPLACE INTO citation_mentions "
                "(mention_id, paper_id, ref_number, page, bbox, context, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"mention_{paper_id}_{index:04d}",
                    paper_id,
                    mention.get("ref_number"),
                    mention.get("page"),
                    mention.get("bbox"),
                    mention.get("context"),
                    mention.get("source") or "grobid",
                ),
            )
    
    def _insert_tables(self, cursor, tables: List[Dict[str, Any]]):
        """Insert tables（V25.14修复: 插入实际 tables 表，而非 figures 表）
        
        实际表结构: table_id, paper_id, table_number, caption, markdown, page
        """
        for table in tables:
            cursor.execute('''
            INSERT OR REPLACE INTO tables 
            (table_id, paper_id, table_number, caption, markdown, page)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                table.get("table_id"),
                table.get("paper_id"),
                table.get("table_number"),
                table.get("caption"),
                table.get("markdown") or table.get("table_data"),
                table.get("page_number") or table.get("page"),
            ))

    # ============================================================
    # Supplementary files (V25.17)
    # ============================================================

    def insert_supplementary_file(self, supp_data: Dict[str, Any]) -> bool:
        """Insert a supplementary file record into the database.
        
        Args:
            supp_data: dict with supp_id, paper_id, filename, file_type, 
                       file_path, file_size, description
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
            INSERT OR REPLACE INTO supplementary_files
            (supp_id, paper_id, filename, file_type, file_path, file_size, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                supp_data.get("supp_id"),
                supp_data.get("paper_id"),
                supp_data.get("filename"),
                supp_data.get("file_type"),
                supp_data.get("file_path"),
                supp_data.get("file_size"),
                supp_data.get("description", ""),
            ))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"❌ Error inserting supplementary file: {e}")
            return False
        finally:
            conn.close()

    def get_supplementary_files(self, paper_id: str) -> List[Dict[str, Any]]:
        """Get all supplementary files for a paper."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
            SELECT supp_id, paper_id, filename, file_type, file_path, 
                   file_size, description, created_at
            FROM supplementary_files
            WHERE paper_id = ?
            ORDER BY created_at
            ''', (paper_id,))
            rows = cursor.fetchall()
            return [
                {
                    "supp_id": r[0],
                    "paper_id": r[1],
                    "filename": r[2],
                    "file_type": r[3],
                    "file_path": r[4],
                    "file_size": r[5],
                    "description": r[6],
                    "created_at": r[7],
                }
                for r in rows
            ]
        except Exception as e:
            print(f"❌ Error getting supplementary files: {e}")
            return []
        finally:
            conn.close()

    def delete_supplementary_file(self, supp_id: str) -> bool:
        """Delete a supplementary file record (does NOT delete the actual file)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM supplementary_files WHERE supp_id = ?", (supp_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            print(f"❌ Error deleting supplementary file: {e}")
            return False
        finally:
            conn.close()

    def get_supplementary_count(self, paper_id: str) -> int:
        """Get count of supplementary files for a paper."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM supplementary_files WHERE paper_id = ?",
                (paper_id,)
            )
            return cursor.fetchone()[0]
        except Exception as e:
            print(f"❌ Error getting supplementary count: {e}")
            return 0
        finally:
            conn.close()
