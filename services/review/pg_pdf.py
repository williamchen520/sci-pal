"""PG-backed PDF/DOCX reports (G3.10e4e)."""

from __future__ import annotations

from services.review import docx_report, pdf_report, pg_report, pg_systematic


def _data(project_id: str):
    project = pg_systematic.get_project(project_id)
    if not project:
        raise KeyError("project not found")
    return (
        project,
        pg_systematic.prisma(project_id),
        pg_systematic.list_evidence(project_id),
        pg_report._rob_rows(project_id),
    )


def render_pdf(project_id: str) -> bytes:
    return pdf_report.render_pdf(None, project_id, data=_data(project_id))


def render_docx(project_id: str) -> bytes:
    return docx_report.render_docx(None, project_id, data=_data(project_id))
