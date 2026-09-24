"""Evidence-backed audit reports (FR-15) with SHA-256 integrity.

AI only detects/prioritises; every dossier carries the human-in-the-loop
statement and the evidence chain hashes so an official can verify provenance.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape as _esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.core.evidence_chain import CHAIN_GENESIS
from app.models.ops import Alert, Case, Evidence, Inspection, Project

_REPORTS_DIR = Path(settings.upload_dir).resolve().parent / "reports"

_INK = colors.HexColor("#1f2937")
_BLUE = colors.HexColor("#1d4ed8")
_LINE = colors.HexColor("#d7dce3")
_AMBER = colors.HexColor("#b45309")
_RED = colors.HexColor("#b91c1c")
_GREEN = colors.HexColor("#15803d")


def _styles() -> dict:
    base = getSampleStyleSheet()
    title = ParagraphStyle("T", parent=base["Title"], fontName="Helvetica-Bold",
                           fontSize=20, textColor=_INK, spaceAfter=2)
    h1 = ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold",
                        fontSize=13, textColor=_INK, spaceBefore=10, spaceAfter=4)
    h2 = ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold",
                        fontSize=11, textColor=_BLUE, spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("B", parent=base["BodyText"], fontName="Helvetica",
                          fontSize=9, leading=12, textColor=_INK, alignment=TA_LEFT)
    small = ParagraphStyle("S", parent=body, fontSize=7.5, leading=9, textColor=colors.HexColor("#4b5563"))
    mono = ParagraphStyle("M", parent=body, fontName="Courier", fontSize=7.5, leading=9)
    return {"title": title, "h1": h1, "h2": h2, "body": body, "small": small, "mono": mono}


def _output_dir() -> Path:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"


def _status_colour(value: str):
    low = {"green", "open", "issued", "verified", "completed", "true_positive", "pass"}
    mid = {"amber", "in_review", "warning", "unknown"}
    if value in low:
        return _GREEN
    if value in mid or value.startswith("verif") or value == "action_taken":
        return _AMBER
    return _RED


def _page_draw(reference: str):
    def draw(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        if settings.demo_mode:
            canvas.setFont("Helvetica-Bold", 46)
            canvas.setFillColor(colors.HexColor("#0a0a0a08"))
            canvas.drawCentredString(A4[0] / 2, A4[1] / 2, "SAMPLE / DEMO")
        canvas.setStrokeColor(_BLUE)
        canvas.setLineWidth(1.2)
        canvas.line(15 * mm, A4[1] - 12 * mm, A4[0] - 15 * mm, A4[1] - 12 * mm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(_BLUE)
        canvas.drawString(15 * mm, A4[1] - 10.4 * mm, "OMNIWATCH — EVIDENCE-BACKED AUDIT REPORT")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawRightString(A4[0] - 15 * mm, A4[1] - 10.4 * mm, f"{reference} · {utc_now_str()}")
        canvas.drawString(15 * mm, 10 * mm, "OMNIWATCH — From Self-Reported Monitoring to Evidence-Backed Verification")
        canvas.setFont("Helvetica-Oblique", 7)
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"p. {doc.page}")
        canvas.restoreState()

    return draw


def utc_now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _table(rows: list[list], widths: list[float | None], header: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
        ("GRID", (0, 0), (-1, -1), 0.4, _LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style))
    return t


def case_dossier(db: Session, case: Case, actor_name: str) -> tuple[Path, str]:
    """Generate a tamper-evident dossier PDF for a case. Returns (path, sha256)."""
    styles = _styles()
    project = db.get(Project, case.project_id) if case.project_id else None
    alerts = db.query(Alert).filter(Alert.case_id == case.id).order_by(Alert.occurred_at).all()
    inspections = db.query(Inspection).filter(
        Inspection.project_id == case.project_id).order_by(Inspection.created_at.desc()).all() \
        if case.project_id else []
    evidence = (db.query(Evidence)
                .filter(Evidence.case_id == case.id)
                .order_by(Evidence.id).all())

    out = _output_dir() / f"dossier-{case.code}-{date.today().isoformat()}.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=A4,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=20 * mm, bottomMargin=16 * mm,
                            title=f"OmniWatch dossier {case.code}",
                            author="OmniWatch")
    story = [Paragraph("OMNIWATCH", styles["title"]),
             Paragraph("Evidence-backed audit dossier · " + _esc(case.title), styles["h1"]),
             HRFlowable(width="100%", thickness=1, color=_BLUE, spaceAfter=8)]

    kv = [
        ["Case", case.code], ["Project", f"{project.name} ({project.code})" if project else "—"],
        ["Status", case.status], ["Opened", _fmt(case.opened_at)],
        ["Generated by", actor_name], ["Generated at", utc_now_str()],
    ]
    story.append(_table([[Paragraph(f"<b>{k}</b>", styles["body"]), Paragraph(_esc(str(v)), styles["body"])]
                         for k, v in kv], [45 * mm, 105 * mm], header=False))
    story.append(Spacer(1, 6))

    story.append(Paragraph("1. Case description", styles["h2"]))
    story.append(Paragraph(_esc(case.description) if case.description else "—", styles["body"]))

    story.append(Paragraph("2. Contributing alerts (signals + explanation)", styles["h2"]))
    if alerts:
        for a in alerts:
            story.append(Paragraph(
                f"<b>[{a.severity.upper()}] {_esc(a.title)}</b> · {_fmt(a.occurred_at)} · "
                f"risk {a.risk_signal:.2f}", styles["body"]))
            story.append(Paragraph(_esc(a.summary), styles["body"]))
            sig_lines = "<br/>".join(
                f"&nbsp;&nbsp;• {_esc(str(s.get('type', '')))}: "
                f"{_esc(str(s.get('observed', s)))}"
                for s in (a.signals or [])[:8])
            if sig_lines:
                story.append(Paragraph(sig_lines, styles["small"]))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No alerts linked to this case.", styles["body"]))

    story.append(Paragraph("3. Field inspections & route integrity", styles["h2"]))
    if inspections:
        rows = [["Code", "Status", "Inspector", "Assigned", "Submitted", "Geofence", "Warnings"]]
        for i in inspections:
            warnings = ", ".join(i.route_warnings or []) or "none"
            rows.append([i.code, i.status, str(i.assigned_inspector_id),
                         _fmt(i.created_at), _fmt(i.submitted_at),
                         f"{i.geofence_radius_m:.0f} m", warnings])
        story.append(_table(rows, [32 * mm, 20 * mm, 18 * mm, 32 * mm, 32 * mm, 16 * mm, 34 * mm]))
    else:
        story.append(Paragraph("No field inspections linked yet.", styles["body"]))

    story.append(Paragraph("4. Evidence chain-of-custody (SHA-256)", styles["h2"]))
    if evidence:
        rows = [["#", "Kind", "Captured", "Geo-ok", "SHA-256", "Chain hash"]]
        prev = CHAIN_GENESIS
        for idx, ev in enumerate(evidence, 1):
            ok = "yes" if ev.geofence_ok else ("no" if ev.geofence_ok is False else "n/a")
            rows.append([str(idx), f"{ev.kind}/{ev.source}", _fmt(ev.captured_at), ok,
                         ev.sha256[:20] + "…", ev.chain_hash[:20] + "…"])
            prev = ev.chain_hash
        story.append(_table(rows, [8 * mm, 26 * mm, 34 * mm, 14 * mm, 42 * mm, 42 * mm]))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"Chain genesis: {CHAIN_GENESIS[:24]}… — every artifact is "
                               f"linked to its predecessor ({len(evidence)} artifacts).",
                               styles["small"]))
    else:
        story.append(Paragraph("No evidence artifacts attached yet.", styles["body"]))

    story.append(PageBreak())
    story.append(Paragraph("5. Human-in-the-loop statement", styles["h2"]))
    story.append(Paragraph(
        "This dossier is generated from machine signals. AI performs DETECTION and "
        "PRIORITISATION only. VERIFICATION and DECISION rest exclusively with "
        "authorised officials. No person, NGO or project is declared fraudulent "
        "solely on the basis of an AI risk score.", styles["body"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Prepared by: " + _esc(actor_name), styles["body"]))
    story.append(Paragraph("Authorised official decision & signature: "
                           "______________________________________", styles["body"]))

    doc.build(story, onFirstPage=_page_draw(case.code), onLaterPages=_page_draw(case.code))
    return out, _sha_file(out)


def end_of_day(db: Session, actor_name: str = "system",
               report_date: date | None = None) -> tuple[Path, str]:
    """End-of-day digest of project health, alerts, inspections and handouts."""
    styles = _styles()
    day = report_date or date.today()
    projects = db.query(Project).order_by(Project.risk_score.desc()).all()

    out = _output_dir() / f"eod-{day.isoformat()}.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=A4,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=20 * mm, bottomMargin=16 * mm,
                            title=f"OmniWatch EOD {day.isoformat()}", author="OmniWatch")
    story = [Paragraph("OMNIWATCH", styles["title"]),
             Paragraph(f"End-of-day operational summary — {day.isoformat()}", styles["h1"]),
             HRFlowable(width="100%", thickness=1, color=_BLUE, spaceAfter=8)]
    if not projects:
        story.append(Paragraph("No projects registered.", styles["body"]))
    rows = [["Project", "Risk", "Score", "Alerts open", "CCTV (frames/events)", "QR consumed"]]
    for p in projects:
        from app.models.ops import QrCode
        from app.models.cv import CctvEvent
        alerts = db.query(Alert).filter(Alert.project_id == p.id,
                                        Alert.status.in_(("open", "in_review", "verifying", "action_taken"))).count()
        cctv = db.query(CctvEvent).filter(CctvEvent.project_id == p.id).count()
        consumed = db.query(QrCode).filter(QrCode.project_id == p.id,
                                           QrCode.status == "consumed").count()
        rows.append([p.name, p.risk_status, f"{p.risk_score:.2f}", str(alerts),
                     str(cctv), str(consumed)])
    story.append(_table(rows, [60 * mm, 18 * mm, 18 * mm, 24 * mm, 40 * mm, 24 * mm]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Digest is advisory. Any alert requiring action is routed to the command queue "
        "and closed only by an authorised official.", styles["small"]))
    doc.build(story, onFirstPage=_page_draw(f"EOD-{day.isoformat()}"),
              onLaterPages=_page_draw(f"EOD-{day.isoformat()}"))
    return out, _sha_file(out)
