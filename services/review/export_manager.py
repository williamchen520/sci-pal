"""
Sci-Pal 导出与分享功能模块 V33.6

用途：提供综述的多格式导出和分享功能。
- 多格式导出：Markdown / PDF / Word / 统计报告 / BibTeX / JSON
- 引用保留：导出时保留引用格式和证据锚定
- 分享链接：生成带过期时间和访问密码的分享链接
- 任务管理：导出任务的创建/查询/下载

设计原则：
- 格式完整：导出文件包含完整的综述内容、引用、参考文献
- 证据可追溯：导出文件中保留证据 ID，方便回查
- 安全分享：分享链接支持过期时间和访问密码
- 异步处理：大文件导出异步处理，不阻塞主流程
"""

import json
import time
import uuid
import threading
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


# =============================================================================
# 数据结构
# =============================================================================

class ExportFormat(str, Enum):
    """导出格式"""
    MARKDOWN = "markdown"
    PDF = "pdf"
    WORD = "word"
    STATS_REPORT = "stats_report"
    BIBTEX = "bibtex"
    JSON = "json"
    PLAIN_TEXT = "plain_text"


class ExportStatus(str, Enum):
    """导出任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class ExportTask:
    """导出任务"""
    task_id: str = field(default_factory=lambda: f"export_{uuid.uuid4().hex[:12]}")
    review_id: str = ""
    format: str = ExportFormat.MARKDOWN.value
    status: str = ExportStatus.PENDING.value
    progress: float = 0.0
    current_step: str = ""

    # 文件信息
    file_name: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    file_url: str = ""

    # 配置
    include_references: bool = True
    include_evidence_ids: bool = False
    citation_style: str = "apa"  # apa / nature / vancouver
    language: str = "en"  # en / zh

    # 时间
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str = ""
    completed_at: str = ""
    expires_at: str = ""  # 导出文件过期时间

    # 错误
    error_message: str = ""

    # 元数据
    metadata: dict = field(default_factory=dict)


@dataclass
class ShareLink:
    """分享链接"""
    link_id: str = field(default_factory=lambda: f"share_{uuid.uuid4().hex[:12]}")
    review_id: str = ""
    export_task_id: str = ""

    # 安全设置
    password_hash: str = ""  # 密码哈希（可选）
    has_password: bool = False
    expires_at: str = ""  # 过期时间
    max_views: int = 0  # 最大访问次数（0 表示不限）
    view_count: int = 0

    # 状态
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_viewed_at: str = ""

    # 元数据
    title: str = ""
    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ExportStats:
    """导出统计信息"""
    total_exports: int = 0
    by_format: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    total_file_size_bytes: int = 0
    avg_processing_seconds: float = 0.0
    total_share_links: int = 0
    active_share_links: int = 0


# =============================================================================
# 导出管理器
# =============================================================================

class ExportManager:
    """
    导出与分享管理器

    用法：
        manager = ExportManager()

        # 创建导出任务
        task = manager.create_export(
            review_id='rev_001',
            format='markdown',
            include_references=True,
        )

        # 执行导出（同步或异步）
        result = manager.export_to_markdown(task, review_data)

        # 查询任务
        task = manager.get_task(task.task_id)

        # 创建分享链接
        link = manager.create_share_link(
            review_id='rev_001',
            export_task_id=task.task_id,
            password='123456',
            expires_in_hours=24,
        )

        # 验证分享链接
        valid = manager.verify_share_link(link.link_id, password='123456')
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_tasks: int = 500,
        default_expiry_hours: int = 72,
    ):
        """
        Args:
            storage_dir: 存储目录，默认 data/exports/
            max_tasks: 最多保留的导出任务数
            default_expiry_hours: 导出文件默认过期时间（小时）
        """
        self.max_tasks = max_tasks
        self.default_expiry_hours = default_expiry_hours
        self._lock = threading.Lock()

        # 存储目录
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(__file__).parent.parent.parent / "data" / "exports"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 导出文件目录
        self._files_dir = self.storage_dir / "files"
        self._files_dir.mkdir(exist_ok=True)

        # 任务和分享链接目录
        self._tasks_dir = self.storage_dir / "tasks"
        self._tasks_dir.mkdir(exist_ok=True)
        self._shares_dir = self.storage_dir / "shares"
        self._shares_dir.mkdir(exist_ok=True)

        # 索引文件
        self._tasks_index_file = self.storage_dir / "tasks_index.json"
        self._shares_index_file = self.storage_dir / "shares_index.json"
        self._tasks_index: list[dict] = self._load_json(self._tasks_index_file, [])
        self._shares_index: list[dict] = self._load_json(self._shares_index_file, [])

    # -------------------------------------------------------------------------
    # 导出任务管理
    # -------------------------------------------------------------------------

    def create_export(
        self,
        review_id: str,
        format: str = ExportFormat.MARKDOWN.value,
        include_references: bool = True,
        include_evidence_ids: bool = False,
        citation_style: str = "apa",
        language: str = "en",
    ) -> ExportTask:
        """创建导出任务"""
        task = ExportTask(
            review_id=review_id,
            format=format,
            include_references=include_references,
            include_evidence_ids=include_evidence_ids,
            citation_style=citation_style,
            language=language,
            expires_at=(datetime.now() + timedelta(hours=self.default_expiry_hours)).isoformat(),
        )
        self._save_task(task)
        return task

    def get_task(self, task_id: str) -> Optional[ExportTask]:
        """获取导出任务"""
        task_file = self._tasks_dir / f"{task_id}.json"
        if task_file.is_file():
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return ExportTask(**data)
            except Exception:
                pass
        return None

    def update_task_progress(
        self,
        task_id: str,
        progress: float,
        current_step: str = "",
    ):
        """更新任务进度"""
        task = self.get_task(task_id)
        if not task:
            return
        task.status = ExportStatus.PROCESSING.value
        if not task.started_at:
            task.started_at = datetime.now().isoformat()
        task.progress = min(progress, 100.0)
        task.current_step = current_step
        self._save_task(task)

    def complete_task(
        self,
        task_id: str,
        file_name: str,
        file_content: str,
    ) -> Optional[ExportTask]:
        """
        完成导出任务（保存文件）

        Args:
            task_id: 任务 ID
            file_name: 文件名
            file_content: 文件内容

        Returns:
            更新后的任务
        """
        task = self.get_task(task_id)
        if not task:
            return None

        # 保存文件
        file_path = self._files_dir / file_name
        try:
            if isinstance(file_content, (bytes, bytearray)):
                with open(file_path, "wb") as f:
                    f.write(file_content)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(file_content)
            file_size = file_path.stat().st_size
        except Exception as e:
            task.status = ExportStatus.FAILED.value
            task.error_message = str(e)
            self._save_task(task)
            return task

        task.status = ExportStatus.COMPLETED.value
        task.progress = 100.0
        task.file_name = file_name
        task.file_path = str(file_path)
        task.file_size_bytes = file_size
        task.completed_at = datetime.now().isoformat()
        self._save_task(task)
        return task

    def fail_task(self, task_id: str, error_message: str):
        """标记任务失败"""
        task = self.get_task(task_id)
        if not task:
            return
        task.status = ExportStatus.FAILED.value
        task.error_message = error_message
        task.completed_at = datetime.now().isoformat()
        self._save_task(task)

    def list_tasks(
        self,
        review_id: str = "",
        status: str = "",
        limit: int = 50,
    ) -> list[ExportTask]:
        """列出导出任务"""
        with self._lock:
            task_ids = [idx["task_id"] for idx in reversed(self._tasks_index)]

        results = []
        for tid in task_ids:
            task = self.get_task(tid)
            if not task:
                continue
            if review_id and task.review_id != review_id:
                continue
            if status and task.status != status:
                continue
            results.append(task)
            if len(results) >= limit:
                break
        return results

    # -------------------------------------------------------------------------
    # 具体格式导出方法
    # -------------------------------------------------------------------------

    def export_to_markdown(
        self,
        task_id: str,
        title: str,
        sections: list[dict],
        references: list[dict] = None,
    ) -> Optional[ExportTask]:
        """
        导出为 Markdown

        Args:
            task_id: 任务 ID
            title: 综述标题
            sections: 章节列表，每个章节包含 title、content、evidence_ids
            references: 参考文献列表

        Returns:
            更新后的任务
        """
        self.update_task_progress(task_id, 10, "正在生成 Markdown...")

        lines = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append(f"*导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 章节内容
        for i, section in enumerate(sections, 1):
            lines.append(f"## {section.get('title', f'Section {i}')}")
            lines.append("")
            content = section.get("content", "")
            lines.append(content)
            lines.append("")

            # 证据 ID（可选）
            task = self.get_task(task_id)
            if task and task.include_evidence_ids:
                evidence_ids = section.get("evidence_ids", [])
                if evidence_ids:
                    lines.append(f"*证据 ID: {', '.join(evidence_ids)}*")
                    lines.append("")

        # 参考文献
        task = self.get_task(task_id)
        if task and task.include_references and references:
            self.update_task_progress(task_id, 50, "正在生成参考文献...")
            lines.append("---")
            lines.append("")
            lines.append("## References")
            lines.append("")
            for i, ref in enumerate(references, 1):
                authors = ref.get("authors", "")
                year = ref.get("year", "")
                title = ref.get("title", "")
                journal = ref.get("journal", "")
                doi = ref.get("doi", "")
                lines.append(f"{i}. {authors} ({year}). {title}. *{journal}*. {doi}")
                lines.append("")

        content = "\n".join(lines)
        file_name = f"{task.review_id}_{task.format}.md"
        self.update_task_progress(task_id, 90, "正在保存文件...")
        return self.complete_task(task_id, file_name, content)

    def export_to_docx(
        self,
        task_id: str,
        title: str,
        sections: list[dict],
        references: list[dict] = None,
    ) -> Optional[ExportTask]:
        """导出为 Word (.docx)。"""
        import io

        from docx import Document

        task = self.get_task(task_id)
        if not task:
            return None

        self.update_task_progress(task_id, 10, "正在生成 Word 文档...")
        document = Document()
        self._docx_header_footer(document, title)
        document.add_heading(title, level=0)
        document.add_paragraph(
            f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        for i, section in enumerate(sections, 1):
            document.add_heading(section.get("title") or f"Section {i}", level=2)
            content = str(section.get("content") or "")
            for block in content.split("\n\n"):
                if block.strip():
                    document.add_paragraph(block.strip())
            if task.include_evidence_ids:
                evidence_ids = section.get("evidence_ids") or []
                if evidence_ids:
                    document.add_paragraph(f"证据 ID: {', '.join(evidence_ids)}")

        if task.include_references and references:
            document.add_page_break()
            document.add_heading("References", level=2)
            for i, ref in enumerate(references, 1):
                document.add_paragraph(
                    f"{i}. {ref.get('authors', '')} ({ref.get('year', '')}). "
                    f"{ref.get('title', '')}. {ref.get('journal', '')}. {ref.get('doi', '')}"
                )

        buffer = io.BytesIO()
        document.save(buffer)
        file_name = f"{task.review_id}_{task.format}.docx"
        self.update_task_progress(task_id, 90, "正在保存文件...")
        return self.complete_task(task_id, file_name, buffer.getvalue())

    @staticmethod
    def _docx_header_footer(document, title: str) -> None:
        """页眉放标题，页脚放「第 X 页」（PAGE 域）。"""
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        section = document.sections[0]
        header = section.header.paragraphs[0] if section.header.paragraphs else section.header.add_paragraph()
        header.text = str(title)[:80]

        footer = section.footer.paragraphs[0] if section.footer.paragraphs else section.footer.add_paragraph()
        footer.text = "第 "
        run = footer.add_run()
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        run._r.addnext(field)
        footer.add_run(" 页")

    def export_to_pdf(
        self,
        task_id: str,
        title: str,
        sections: list[dict],
        references: list[dict] = None,
    ) -> Optional[ExportTask]:
        """导出为 PDF（reportlab；无 LibreOffice 依赖）。"""
        import io

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

        task = self.get_task(task_id)
        if not task:
            return None

        self.update_task_progress(task_id, 10, "正在生成 PDF...")
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            font = "STSong-Light"
        except Exception:  # noqa: BLE001 - fall back to Helvetica
            font = "Helvetica"

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReviewTitle", parent=styles["Title"], fontName=font, fontSize=18, leading=22
        )
        heading_style = ParagraphStyle(
            "ReviewHeading", parent=styles["Heading2"], fontName=font, fontSize=13, leading=16
        )
        body_style = ParagraphStyle(
            "ReviewBody", parent=styles["BodyText"], fontName=font, fontSize=10, leading=14
        )
        meta_style = ParagraphStyle(
            "ReviewMeta", parent=body_style, fontSize=8, textColor="#666666"
        )

        def escape(text: str) -> str:
            return (
                str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        story = [Paragraph(escape(title), title_style), Spacer(1, 4 * mm)]
        story.append(
            Paragraph(
                f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style
            )
        )
        story.append(Spacer(1, 6 * mm))

        for i, section in enumerate(sections, 1):
            story.append(Paragraph(escape(section.get("title") or f"Section {i}"), heading_style))
            for block in str(section.get("content") or "").split("\n\n"):
                if block.strip():
                    story.append(Paragraph(escape(block.strip()), body_style))
                    story.append(Spacer(1, 2 * mm))
            if task.include_evidence_ids:
                evidence_ids = section.get("evidence_ids") or []
                if evidence_ids:
                    story.append(
                        Paragraph(f"证据 ID: {escape(', '.join(evidence_ids))}", meta_style)
                    )

        if task.include_references and references:
            story.append(PageBreak())
            story.append(Paragraph("References", heading_style))
            for i, ref in enumerate(references, 1):
                story.append(
                    Paragraph(
                        escape(
                            f"{i}. {ref.get('authors', '')} ({ref.get('year', '')}). "
                            f"{ref.get('title', '')}. {ref.get('journal', '')}. {ref.get('doi', '')}"
                        ),
                        body_style,
                    )
                )

        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=A4, title=str(title))

        def draw_header_footer(canvas, doc):
            canvas.saveState()
            canvas.setFont(font, 8)
            canvas.drawString(20 * mm, A4[1] - 12 * mm, str(title)[:90])
            canvas.drawCentredString(A4[0] / 2, 10 * mm, f"第 {doc.page} 页")
            canvas.restoreState()

        document.build(story, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
        file_name = f"{task.review_id}_{task.format}.pdf"
        self.update_task_progress(task_id, 90, "正在保存文件...")
        return self.complete_task(task_id, file_name, buffer.getvalue())

    def export_to_bibtex(
        self,
        task_id: str,
        references: list[dict],
    ) -> Optional[ExportTask]:
        """
        导出为 BibTeX

        Args:
            task_id: 任务 ID
            references: 参考文献列表

        Returns:
            更新后的任务
        """
        self.update_task_progress(task_id, 10, "正在生成 BibTeX...")

        lines = []
        for i, ref in enumerate(references, 1):
            ref_type = ref.get("type", "article")
            key = ref.get("key", f"ref{i}")
            lines.append(f"@{ref_type}{{{key},")
            for field_name in ["author", "title", "journal", "year", "volume", "number", "pages", "doi", "publisher"]:
                value = ref.get(field_name, "")
                if value:
                    lines.append(f"  {field_name} = {{{value}}},")
            lines.append("}")
            lines.append("")

        content = "\n".join(lines)
        file_name = f"{task_id}_references.bib"
        return self.complete_task(task_id, file_name, content)

    def export_to_json(
        self,
        task_id: str,
        review_data: dict,
    ) -> Optional[ExportTask]:
        """
        导出为 JSON（完整数据）

        Args:
            task_id: 任务 ID
            review_data: 综述完整数据

        Returns:
            更新后的任务
        """
        self.update_task_progress(task_id, 50, "正在生成 JSON...")
        content = json.dumps(review_data, ensure_ascii=False, indent=2)
        file_name = f"{task_id}_data.json"
        return self.complete_task(task_id, file_name, content)

    def export_to_plain_text(
        self,
        task_id: str,
        title: str,
        sections: list[dict],
        references: list[dict] = None,
    ) -> Optional[ExportTask]:
        """导出为纯文本"""
        self.update_task_progress(task_id, 10, "正在生成纯文本...")

        lines = []
        lines.append("=" * 60)
        lines.append(title)
        lines.append("=" * 60)
        lines.append("")

        for i, section in enumerate(sections, 1):
            lines.append(f"[{i}] {section.get('title', '')}")
            lines.append("-" * 40)
            lines.append(section.get("content", ""))
            lines.append("")

        if references:
            lines.append("=" * 60)
            lines.append("References")
            lines.append("=" * 60)
            for i, ref in enumerate(references, 1):
                lines.append(f"[{i}] {ref.get('authors', '')} ({ref.get('year', '')}). {ref.get('title', '')}")

        content = "\n".join(lines)
        file_name = f"{task_id}_text.txt"
        return self.complete_task(task_id, file_name, content)

    # -------------------------------------------------------------------------
    # 分享链接管理
    # -------------------------------------------------------------------------

    def create_share_link(
        self,
        review_id: str,
        export_task_id: str = "",
        password: str = "",
        expires_in_hours: int = 24,
        max_views: int = 0,
        title: str = "",
        description: str = "",
    ) -> ShareLink:
        """
        创建分享链接

        Args:
            review_id: 综述 ID
            export_task_id: 关联的导出任务 ID
            password: 访问密码（可选，空表示无密码）
            expires_in_hours: 过期时间（小时）
            max_views: 最大访问次数（0 表示不限）
            title: 分享标题
            description: 分享描述

        Returns:
            分享链接对象
        """
        link = ShareLink(
            review_id=review_id,
            export_task_id=export_task_id,
            has_password=bool(password),
            password_hash=self._hash_password(password) if password else "",
            expires_at=(datetime.now() + timedelta(hours=expires_in_hours)).isoformat(),
            max_views=max_views,
            title=title,
            description=description,
        )
        self._save_share_link(link)
        return link

    def verify_share_link(
        self,
        link_id: str,
        password: str = "",
    ) -> tuple[bool, str]:
        """
        验证分享链接

        Returns:
            (是否有效, 原因说明)
        """
        link = self.get_share_link(link_id)
        if not link:
            return False, "分享链接不存在"

        if not link.is_active:
            return False, "分享链接已被禁用"

        # 检查过期
        try:
            expires_at = datetime.fromisoformat(link.expires_at)
            if datetime.now() > expires_at:
                link.is_active = False
                self._save_share_link(link)
                return False, "分享链接已过期"
        except Exception:
            pass

        # 检查访问次数
        if link.max_views > 0 and link.view_count >= link.max_views:
            return False, "分享链接已达到最大访问次数"

        # 检查密码
        if link.has_password:
            if not password:
                return False, "需要访问密码"
            if self._hash_password(password) != link.password_hash:
                return False, "访问密码错误"

        # 验证通过，更新访问计数
        link.view_count += 1
        link.last_viewed_at = datetime.now().isoformat()
        self._save_share_link(link)
        return True, "验证通过"

    def get_share_link(self, link_id: str) -> Optional[ShareLink]:
        """获取分享链接"""
        link_file = self._shares_dir / f"{link_id}.json"
        if link_file.is_file():
            try:
                with open(link_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return ShareLink(**data)
            except Exception:
                pass
        return None

    def revoke_share_link(self, link_id: str) -> bool:
        """撤销分享链接"""
        link = self.get_share_link(link_id)
        if not link:
            return False
        link.is_active = False
        self._save_share_link(link)
        return True

    def list_share_links(
        self,
        review_id: str = "",
        active_only: bool = False,
        limit: int = 50,
    ) -> list[ShareLink]:
        """列出分享链接"""
        with self._lock:
            link_ids = [idx["link_id"] for idx in reversed(self._shares_index)]

        results = []
        for lid in link_ids:
            link = self.get_share_link(lid)
            if not link:
                continue
            if review_id and link.review_id != review_id:
                continue
            if active_only and not link.is_active:
                continue
            results.append(link)
            if len(results) >= limit:
                break
        return results

    # -------------------------------------------------------------------------
    # 统计
    # -------------------------------------------------------------------------

    def get_stats(self) -> ExportStats:
        """获取导出统计信息"""
        with self._lock:
            tasks = [self.get_task(idx["task_id"]) for idx in self._tasks_index]
            shares = [self.get_share_link(idx["link_id"]) for idx in self._shares_index]

        tasks = [t for t in tasks if t]
        shares = [s for s in shares if s]

        stats = ExportStats(
            total_exports=len(tasks),
            total_share_links=len(shares),
            active_share_links=sum(1 for s in shares if s.is_active),
        )

        for t in tasks:
            stats.by_format[t.format] = stats.by_format.get(t.format, 0) + 1
            stats.by_status[t.status] = stats.by_status.get(t.status, 0) + 1
            stats.total_file_size_bytes += t.file_size_bytes

        completed = [t for t in tasks if t.status == ExportStatus.COMPLETED.value and t.started_at and t.completed_at]
        if completed:
            durations = []
            for t in completed:
                try:
                    start = datetime.fromisoformat(t.started_at)
                    end = datetime.fromisoformat(t.completed_at)
                    durations.append((end - start).total_seconds())
                except Exception:
                    pass
            if durations:
                stats.avg_processing_seconds = sum(durations) / len(durations)

        return stats

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _hash_password(self, password: str) -> str:
        """密码哈希"""
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _save_task(self, task: ExportTask):
        """保存任务"""
        try:
            task_file = self._tasks_dir / f"{task.task_id}.json"
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(asdict(task), f, ensure_ascii=False, indent=2)

            with self._lock:
                existing = next((i for i, idx in enumerate(self._tasks_index) if idx["task_id"] == task.task_id), None)
                task_idx = {
                    "task_id": task.task_id,
                    "review_id": task.review_id,
                    "format": task.format,
                    "status": task.status,
                    "created_at": task.created_at,
                }
                if existing is not None:
                    self._tasks_index[existing] = task_idx
                else:
                    self._tasks_index.append(task_idx)

                if len(self._tasks_index) > self.max_tasks:
                    old = self._tasks_index[:-self.max_tasks]
                    for o in old:
                        f = self._tasks_dir / f"{o['task_id']}.json"
                        if f.is_file():
                            f.unlink()
                    self._tasks_index = self._tasks_index[-self.max_tasks:]

                self._save_json(self._tasks_index_file, self._tasks_index)
        except Exception as e:
            print(f"⚠️  保存导出任务失败: {e}")

    def _save_share_link(self, link: ShareLink):
        """保存分享链接"""
        try:
            link_file = self._shares_dir / f"{link.link_id}.json"
            with open(link_file, "w", encoding="utf-8") as f:
                json.dump(asdict(link), f, ensure_ascii=False, indent=2)

            with self._lock:
                existing = next((i for i, idx in enumerate(self._shares_index) if idx["link_id"] == link.link_id), None)
                link_idx = {
                    "link_id": link.link_id,
                    "review_id": link.review_id,
                    "is_active": link.is_active,
                    "created_at": link.created_at,
                }
                if existing is not None:
                    self._shares_index[existing] = link_idx
                else:
                    self._shares_index.append(link_idx)

                self._save_json(self._shares_index_file, self._shares_index)
        except Exception as e:
            print(f"⚠️  保存分享链接失败: {e}")

    def _load_json(self, file_path: Path, default):
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_json(self, file_path: Path, data):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# =============================================================================
# 全局单例
# =============================================================================

_export_manager_instance: Optional[ExportManager] = None
_export_manager_lock = threading.Lock()


def get_export_manager() -> ExportManager:
    """获取全局导出管理器单例"""
    global _export_manager_instance
    if _export_manager_instance is None:
        with _export_manager_lock:
            if _export_manager_instance is None:
                _export_manager_instance = ExportManager()
    return _export_manager_instance
