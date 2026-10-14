"""V25.10 - PDF 标注服务（基于 PyMuPDF）

功能：
1. 向 PDF 文件写入高亮/下划线/批注注释
2. 从 PDF 文件删除指定注释
3. 注释直接写入 PDF 文件，持久化保存，任何 PDF 阅读器都能看到

依赖：PyMuPDF (fitz) — pip install PyMuPDF

坐标系统：使用 PDF 标准坐标（左下角为原点），与 PyMuPDF 一致。
前端 PDF.js 使用左上角坐标，需在前端转换后再发送。
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 注释类型映射
ANNOT_TYPES = {
    "highlight": 8,   # fitz.PDF_ANNOT_HIGHLIGHT
    "underline": 9,   # fitz.PDF_ANNOT_UNDERLINE
    "text": 0,        # fitz.PDF_ANNOT_TEXT (sticky note)
}

# 坐标匹配容差（点）
RECT_TOLERANCE = 3.0


class PdfAnnotator:
    """PDF 标注管理器：写入和删除 PDF 文件中的注释。"""

    def __init__(self, db_path: str, documents_dir: str):
        """
        Args:
            db_path: SQLite 数据库路径（用于查询 paper_id 对应的文件名）
            documents_dir: PDF 文件存储目录
        """
        self.db_path = Path(db_path)
        self.documents_dir = Path(documents_dir)

    def get_pdf_path(self, paper_id: str) -> Optional[Path]:
        """根据 paper_id 查询 PDF 文件路径。"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # V25.13 修复：否则 row["filename"] 报 TypeError
            row = conn.execute(
                "SELECT filename FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            conn.close()
            if not row or not row["filename"]:
                return None
            pdf_path = self.documents_dir / row["filename"]
            return pdf_path if pdf_path.exists() else None
        except Exception as e:
            logger.error(f"查询 PDF 路径失败: {e}")
            return None

    def add_annotation(
        self,
        paper_id: str,
        page: int,
        annot_type: str,
        rect: list,
        color: Optional[list] = None,
        text: str = "",
    ) -> dict:
        """向 PDF 添加注释。

        Args:
            paper_id: 论文 ID
            page: 页码（从 1 开始）
            annot_type: 注释类型：highlight / underline / text
            rect: 注释矩形 [x0, y0, x1, y1]，PDF 标准坐标（左下原点）
            color: RGB 颜色 [r, g, b]，取值 0-1，默认黄色高亮
            text: 注释文本（批注内容或高亮的文字）

        Returns:
            {"success": True, "annotation_id": "..."} 或 {"success": False, "error": "..."}
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return {"success": False, "error": "PyMuPDF 未安装，请执行 pip install PyMuPDF"}

        if annot_type not in ANNOT_TYPES:
            return {"success": False, "error": f"不支持的注释类型: {annot_type}"}

        pdf_path = self.get_pdf_path(paper_id)
        if not pdf_path:
            return {"success": False, "error": f"PDF 文件不存在: {paper_id}"}

        try:
            doc = fitz.open(str(pdf_path))
            if page < 1 or page > doc.page_count:
                doc.close()
                return {"success": False, "error": f"页码超出范围: {page}/{doc.page_count}"}

            page_obj = doc[page - 1]
            r = fitz.Rect(rect[0], rect[1], rect[2], rect[3])

            # 默认颜色
            if color is None:
                if annot_type == "highlight":
                    color = [1.0, 0.9, 0.3]  # 黄色
                elif annot_type == "underline":
                    color = [0.0, 0.4, 1.0]  # 蓝色
                else:
                    color = [1.0, 0.9, 0.3]

            annot = None
            if annot_type == "highlight":
                annot = page_obj.add_highlight_annot(r)
            elif annot_type == "underline":
                annot = page_obj.add_underline_annot(r)
            elif annot_type == "text":
                # 批注（sticky note）放在矩形左上角
                point = fitz.Point(rect[0], rect[3])
                annot = page_obj.add_text_annot(point, text or "Note")

            if annot:
                annot.set_colors(stroke=color)
                if text:
                    annot.set_info(content=text)
                annot.update()

            # 保存（增量保存，更快）
            try:
                doc.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            except Exception:
                # 增量保存失败时用完整保存
                doc.save(str(pdf_path))
            doc.close()

            annotation_id = f"{annot_type}_{page}_{rect[0]:.0f}_{rect[1]:.0f}"
            logger.info(f"添加注释成功: paper={paper_id}, page={page}, type={annot_type}")
            return {"success": True, "annotation_id": annotation_id}

        except Exception as e:
            logger.error(f"添加注释失败: {e}")
            return {"success": False, "error": str(e)}

    def delete_annotation(
        self,
        paper_id: str,
        page: int,
        annot_type: str,
        rect: list,
        text: str = "",
    ) -> dict:
        """从 PDF 删除注释（按页码+类型+矩形+文本匹配）。

        Args:
            paper_id: 论文 ID
            page: 页码（从 1 开始）
            annot_type: 注释类型
            rect: 注释矩形 [x0, y0, x1, y1]
            text: 注释文本（用于精确匹配）

        Returns:
            {"success": True, "deleted": count} 或 {"success": False, "error": "..."}
        """
        try:
            import fitz
        except ImportError:
            return {"success": False, "error": "PyMuPDF 未安装，请执行 pip install PyMuPDF"}

        if annot_type not in ANNOT_TYPES:
            return {"success": False, "error": f"不支持的注释类型: {annot_type}"}

        pdf_path = self.get_pdf_path(paper_id)
        if not pdf_path:
            return {"success": False, "error": f"PDF 文件不存在: {paper_id}"}

        try:
            doc = fitz.open(str(pdf_path))
            if page < 1 or page > doc.page_count:
                doc.close()
                return {"success": False, "error": f"页码超出范围: {page}/{doc.page_count}"}

            page_obj = doc[page - 1]
            target_type = ANNOT_TYPES[annot_type]
            deleted = 0

            for annot in page_obj.annots() or []:
                # 匹配类型
                if annot.type[0] != target_type:
                    continue

                # 匹配矩形（带容差）
                ar = annot.rect
                if (abs(ar.x0 - rect[0]) > RECT_TOLERANCE or
                    abs(ar.y0 - rect[1]) > RECT_TOLERANCE or
                    abs(ar.x1 - rect[2]) > RECT_TOLERANCE or
                    abs(ar.y1 - rect[3]) > RECT_TOLERANCE):
                    continue

                # 如果提供了文本，匹配文本内容
                if text:
                    info = annot.info or {}
                    content = info.get("content", "")
                    if text not in content and content not in text:
                        continue

                # 删除
                page_obj.delete_annot(annot)
                deleted += 1
                break  # 只删第一个匹配的

            if deleted > 0:
                try:
                    doc.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                except Exception:
                    doc.save(str(pdf_path))

            doc.close()
            logger.info(f"删除注释: paper={paper_id}, page={page}, type={annot_type}, deleted={deleted}")
            return {"success": True, "deleted": deleted}

        except Exception as e:
            logger.error(f"删除注释失败: {e}")
            return {"success": False, "error": str(e)}

    def list_annotations(self, paper_id: str, page: Optional[int] = None) -> dict:
        """列出 PDF 中的所有注释（用于调试和前端展示）。

        Args:
            paper_id: 论文 ID
            page: 页码（可选，不填则列出所有页）

        Returns:
            {"success": True, "annotations": [...]}
        """
        try:
            import fitz
        except ImportError:
            return {"success": False, "error": "PyMuPDF 未安装"}

        pdf_path = self.get_pdf_path(paper_id)
        if not pdf_path:
            return {"success": False, "error": f"PDF 文件不存在: {paper_id}"}

        try:
            doc = fitz.open(str(pdf_path))
            annotations = []
            pages_to_check = [page - 1] if page else range(doc.page_count)

            for pidx in pages_to_check:
                if pidx < 0 or pidx >= doc.page_count:
                    continue
                page_obj = doc[pidx]
                for annot in page_obj.annots() or []:
                    info = annot.info or {}
                    annotations.append({
                        "page": pidx + 1,
                        "type": annot.type[1],  # 类型名称
                        "type_id": annot.type[0],
                        "rect": [annot.rect.x0, annot.rect.y0, annot.rect.x1, annot.rect.y1],
                        "content": info.get("content", ""),
                        "title": info.get("title", ""),
                    })

            doc.close()
            return {"success": True, "annotations": annotations}
        except Exception as e:
            return {"success": False, "error": str(e)}
