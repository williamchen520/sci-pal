"""PDF report for a systematic review project (ReportLab + CJK font)."""

from __future__ import annotations

import io
import sqlite3
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.review import risk_of_bias, systematic

FONT = "STSong-Light"


def _register() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _p(text: str, style) -> Paragraph:
    return Paragraph(escape(str(text or "")), style)


def render_pdf(conn: sqlite3.Connection, project_id: str) -> bytes:
    _register()
    project = systematic.get_project(conn, project_id)
    if not project:
        raise KeyError("project not found")
    counts = systematic.prisma(conn, project_id)
    evidence = systematic.list_evidence(conn, project_id)
    rob_rows = risk_of_bias.list_rows(conn, project_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=project.get("name") or project_id,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("CJKTitle", parent=styles["Title"], fontName=FONT, fontSize=18, leading=24)
    heading = ParagraphStyle("CJKHeading", parent=styles["Heading2"], fontName=FONT, fontSize=13, leading=18)
    body = ParagraphStyle("CJKBody", parent=styles["BodyText"], fontName=FONT, fontSize=9, leading=13)
    small = ParagraphStyle("CJKSmall", parent=body, fontSize=7.5, leading=10)

    story = [
        _p(project.get("name") or project_id, title),
        _p(f"项目：{project_id}    领域：{project.get('field_text') or '未填写'}", body),
        Spacer(1, 8),
        _p("PICO", heading),
    ]
    pico = project.get("pico") or {}
    for key in ("population", "intervention", "comparator", "outcome"):
        story.append(_p(f"{key}: {pico.get(key) or '未填写'}", body))

    story.append(Spacer(1, 8))
    story.append(_p("PRISMA", heading))
    prisma_data = [["指标", "数量"]] + [
        [key, str(counts.get(key, 0))]
        for key in ("identified", "screened", "included", "excluded", "pending")
    ]
    prisma_table = Table(prisma_data, colWidths=[70 * mm, 40 * mm])
    prisma_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ]
        )
    )
    story.append(prisma_table)

    story.append(Spacer(1, 8))
    story.append(_p("证据表", heading))
    if evidence:
        data = [["Paper", "Design", "Sample", "Intervention", "Comparator", "Effect"]]
        for row in evidence:
            data.append(
                [
                    _p(row.get("paper_id", ""), small),
                    _p(row.get("design", ""), small),
                    _p(row.get("sample_size", ""), small),
                    _p(row.get("intervention", ""), small),
                    _p(row.get("comparator", ""), small),
                    _p(row.get("effect", ""), small),
                ]
            )
        table = Table(data, colWidths=[50 * mm, 28 * mm, 18 * mm, 32 * mm, 32 * mm, 20 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
    else:
        story.append(_p("暂无证据行。", body))

    story.append(Spacer(1, 8))
    story.append(_p("风险偏倚", heading))
    if rob_rows:
        by_paper = {}
        for row in rob_rows:
            by_paper.setdefault(row["paper_id"], []).append(row)
        data = [["Paper", "Overall"]]
        for paper, items in by_paper.items():
            data.append([_p(paper, small), _p(risk_of_bias.overall(items), small)])
        table = Table(data, colWidths=[90 * mm, 30 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ]
            )
        )
        story.append(table)
    else:
        story.append(_p("暂无风险评估。", body))

    story.append(Spacer(1, 10))
    story.append(_p("Generated by SciPal systematic review", small))
    doc.build(story)
    return buffer.getvalue()
