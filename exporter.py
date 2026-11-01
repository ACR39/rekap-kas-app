"""Pembuatan file PDF rekap pengeluaran (ReportLab)."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ACCENT = colors.HexColor("#1F6F5C")
HEAD_BG = colors.HexColor("#1F6F5C")
ROW_ALT = colors.HexColor("#F1EDE4")
GRID = colors.HexColor("#D8D2C6")


def _safe(text: object) -> str:
    """Helvetica bawaan PDF hanya mendukung latin-1."""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _rupiah(value: int | float) -> str:
    return "Rp " + f"{int(round(value)):,}".replace(",", ".")


def build_pdf(transactions: list[dict], period_label: str, owner_label: str = "pribadi") -> bytes:
    """transactions: list of dict dengan key tx_date, category, description, amount."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=_safe(f"Rekap Pengeluaran {period_label}"),
        author=_safe(owner_label),
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16, leading=20, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#5A554B"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10)
    cell_bold = ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8, leading=10)
    head_cell = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white)

    total = sum(int(t["amount"]) for t in transactions)
    story: list = [
        Paragraph("Rekap Pengeluaran", h1),
        Paragraph(
            _safe(f"Periode: {period_label} &nbsp;|&nbsp; "
                  f"Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}"),
            sub,
        ),
        Spacer(1, 8),
    ]

    # ---- ringkasan
    by_cat: dict[str, int] = {}
    for t in transactions:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + int(t["amount"])
    ordered = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)

    story.append(Paragraph("Ringkasan per kategori", h2))
    summary_rows = [[Paragraph("Kategori", head_cell), Paragraph("Nominal", head_cell)]]
    for cat, amount in ordered:
        summary_rows.append([Paragraph(_safe(cat), cell), Paragraph(_rupiah(amount), cell)])
    summary_rows.append([Paragraph("TOTAL", cell_bold), Paragraph(_rupiah(total), cell_bold)])

    summary_table = Table(summary_rows, colWidths=[110 * mm, 45 * mm], repeatRows=1)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, ROW_ALT]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E7E2D6")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ACCENT),
            ]
        )
    )
    story.append(summary_table)

    # ---- rincian transaksi
    story.append(Paragraph("Rincian transaksi", h2))
    detail_rows = [
        [
            Paragraph("Tanggal", head_cell),
            Paragraph("Kategori", head_cell),
            Paragraph("Keterangan", head_cell),
            Paragraph("Nominal", head_cell),
        ]
    ]
    for t in sorted(transactions, key=lambda r: (r["tx_date"], r["id"])):
        try:
            tanggal = datetime.strptime(t["tx_date"], "%Y-%m-%d").strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            tanggal = str(t["tx_date"])
        detail_rows.append(
            [
                Paragraph(tanggal, cell),
                Paragraph(_safe(t["category"]), cell),
                Paragraph(_safe(t["description"] or "-"), cell),
                Paragraph(_rupiah(t["amount"]), cell),
            ]
        )

    detail_table = Table(
        detail_rows, colWidths=[20 * mm, 35 * mm, 80 * mm, 25 * mm], repeatRows=1
    )
    detail_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
            ]
        )
    )
    story.append(detail_table)

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#8A8478"))
        canvas.drawString(15 * mm, 10 * mm, _safe(f"Rekap Bayar Kas - {owner_label}"))
        canvas.drawRightString(
            A4[0] - 15 * mm, 10 * mm, f"Halaman {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
