#!/usr/bin/env python3
"""Generate EN + UK Red MMO environment-artist handoff PDFs (artist-facing only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path(r"C:\Windows\Fonts\tahoma.ttf"),
]


def register_fonts() -> tuple[str, str]:
    for path in FONT_CANDIDATES:
        if path.exists():
            pdfmetrics.registerFont(TTFont("Handoff", str(path)))
            bold = path.with_name(path.stem + "bd.ttf")
            if not bold.exists():
                bold = Path(r"C:\Windows\Fonts\arialbd.ttf")
            if bold.exists():
                pdfmetrics.registerFont(TTFont("Handoff-Bold", str(bold)))
                return "Handoff", "Handoff-Bold"
            return "Handoff", "Handoff"
    print("WARN: no TTF found; Cyrillic may fail", file=sys.stderr)
    return "Helvetica", "Helvetica-Bold"


def md_inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font face='Courier' size='8'>\1</font>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<link href='\2'>\1</link>", text)
    return text


def parse_table(lines: list[str], styles) -> Table:
    rows = []
    for line in lines:
        if re.match(r"^\|?\s*-+", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append([Paragraph(md_inline(c), styles["TableCell"]) for c in cells])
    t = Table(rows, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.whitesmoke, colors.Color(0.95, 0.95, 0.97)],
                ),
            ]
        )
    )
    return t


def md_to_flowables(text: str, styles) -> list:
    flow = []
    lines = text.splitlines()
    i = 0
    in_code = False
    code_buf: list[str] = []
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                flow.append(Preformatted("\n".join(code_buf), styles["CodeBlock"]))
                flow.append(Spacer(1, 6))
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*-+", lines[i + 1]):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            flow.append(parse_table(table_lines, styles))
            flow.append(Spacer(1, 8))
            continue
        if line.startswith("# "):
            flow.append(Paragraph(md_inline(line[2:]), styles["DocTitle"]))
        elif line.startswith("## "):
            flow.append(Spacer(1, 10))
            flow.append(Paragraph(md_inline(line[3:]), styles["DocH1"]))
        elif line.startswith("### "):
            flow.append(Paragraph(md_inline(line[4:]), styles["DocH2"]))
        elif line.startswith("---"):
            flow.append(Spacer(1, 8))
        elif line.startswith("- ") or line.startswith("* "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("* ")):
                items.append(ListItem(Paragraph(md_inline(lines[i][2:]), styles["Body"])))
                i += 1
            flow.append(ListFlowable(items, bulletType="bullet", leftIndent=12))
            continue
        elif re.match(r"^\d+\.\s", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i]):
                items.append(
                    ListItem(
                        Paragraph(md_inline(re.sub(r"^\d+\.\s", "", lines[i])), styles["Body"])
                    )
                )
                i += 1
            flow.append(ListFlowable(items, bulletType="1", leftIndent=12))
            continue
        elif line.strip() == "":
            flow.append(Spacer(1, 4))
        else:
            flow.append(Paragraph(md_inline(line), styles["Body"]))
        i += 1
    return flow


def build_styles(font: str, font_bold: str):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(name="Body", fontName=font, fontSize=9, leading=12, spaceAfter=3)
    )
    styles.add(
        ParagraphStyle(
            name="CodeBlock",
            fontName="Courier",
            fontSize=7.5,
            leading=9,
            backColor=colors.HexColor("#f3f4f6"),
            leftIndent=4,
            rightIndent=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            fontName=font,
            fontSize=7.5,
            leading=9,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocTitle",
            fontName=font_bold,
            fontSize=14,
            leading=17,
            spaceAfter=8,
            textColor=colors.HexColor("#111827"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocH1",
            fontName=font_bold,
            fontSize=11,
            leading=14,
            spaceBefore=6,
            textColor=colors.HexColor("#111827"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocH2",
            fontName=font_bold,
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#1f2937"),
        )
    )
    return styles


def build_pdf(out: Path, sources: list[Path], title: str, blurb: str, font: str, font_bold: str) -> None:
    styles = build_styles(font, font_bold)
    doc = SimpleDocTemplate(
        str(out),
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=title,
        author="Red MMO environment artist handoff",
    )
    story = [
        Paragraph(title, styles["DocTitle"]),
        Paragraph(md_inline(blurb), styles["Body"]),
        Spacer(1, 10),
    ]
    for idx, path in enumerate(sources):
        if not path.exists():
            print(f"WARN: missing {path}", file=sys.stderr)
            continue
        if idx:
            story.append(PageBreak())
        story.extend(md_to_flowables(path.read_text(encoding="utf-8"), styles))
    doc.build(story)
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


def main() -> None:
    font, font_bold = register_fonts()
    # Artist-facing only: same-repo merge-safe ownership first.
    en_sources = [
        ROOT / "START_HERE.md",
        ROOT / "MERGE_ENV_AND_GAMEPLAY.md",
        ROOT / "ENVIRONMENT_ARTIST_HANDOFF.md",
        ROOT / "MAPS.md",
        ROOT / "FOLDER_OWNERSHIP.md",
        ROOT / "ENV_FAB_INVENTORY.md",
    ]
    uk_sources = [
        ROOT / "START_HERE_UK.md",
        ROOT / "MERGE_ENV_AND_GAMEPLAY_UK.md",
        ROOT / "ENVIRONMENT_ARTIST_HANDOFF_UK.md",
        ROOT / "MAPS.md",
        ROOT / "FOLDER_OWNERSHIP.md",
        ROOT / "ENV_FAB_INVENTORY.md",
    ]
    build_pdf(
        ROOT / "RedMMO_Environment_Artist_Handoff.pdf",
        en_sources,
        "Red MMO — Environment Artist Handoff (EN)",
        "2026-08-07. Same-repo collaboration: own `L_Hub_Env_Visuals`; "
        "developer owns HubLogic (`L_Hub_Gameplay_Logic`); thin `L_Hub_Persistent` composes both. "
        "Test maps: ArtistCanvas + Sandbox_DesertDemoSparkle_T01. "
        "Clone RedMMOTitan-DeveloperHandoff (same repo as gameplay).",
        font,
        font_bold,
    )
    build_pdf(
        ROOT / "RedMMO_Environment_Artist_Handoff_UK.pdf",
        uk_sources,
        "Red MMO — Передача художнику середовища (UK)",
        "2026-08-07. Спільне репо: володій `L_Hub_Env_Visuals`; "
        "розробник володіє HubLogic (`L_Hub_Gameplay_Logic`); тонкий `L_Hub_Persistent` збирає обидва. "
        "Тестові карти: ArtistCanvas + Sandbox_DesertDemoSparkle_T01. "
        "Клон RedMMOTitan-DeveloperHandoff (те саме репо, що в геймплею).",
        font,
        font_bold,
    )


if __name__ == "__main__":
    main()
