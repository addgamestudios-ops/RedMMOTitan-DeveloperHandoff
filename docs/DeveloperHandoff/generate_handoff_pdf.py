#!/usr/bin/env python3
"""Generate RedMMOTitan_Developer_Handoff.pdf from the handoff markdown set."""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
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
from reportlab.lib import colors

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "RedMMOTitan_Developer_Handoff.pdf"

SOURCES = [
    ROOT / "START_HERE.md",
    ROOT / "DEVELOPER_HANDOFF.md",
    ROOT / "PPG_PLANETGEN_FREE_START.md",
    ROOT / "FAB_MARKETPLACE_INVENTORY.md",
    ROOT / "GITHUB_ACCESS.md",
]


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
    t = Table(rows, hAlign="LEFT", colWidths=None)
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
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.Color(0.95, 0.95, 0.97)]),
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
            flow.append(Paragraph(md_inline(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            flow.append(Spacer(1, 10))
            flow.append(Paragraph(md_inline(line[3:]), styles["Heading1"]))
        elif line.startswith("### "):
            flow.append(Paragraph(md_inline(line[4:]), styles["Heading2"]))
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
                items.append(ListItem(Paragraph(md_inline(re.sub(r"^\d+\.\s", "", lines[i])), styles["Body"])))
                i += 1
            flow.append(ListFlowable(items, bulletType="1", leftIndent=12))
            continue
        elif line.strip() == "":
            flow.append(Spacer(1, 4))
        else:
            flow.append(Paragraph(md_inline(line), styles["Body"]))
        i += 1
    return flow


def main() -> None:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            spaceAfter=3,
        )
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
            fontSize=7.5,
            leading=9,
            alignment=TA_LEFT,
        )
    )
    styles["Title"].fontSize = 16
    styles["Title"].spaceAfter = 8
    styles["Heading1"].fontSize = 12
    styles["Heading1"].spaceBefore = 6
    styles["Heading1"].textColor = colors.HexColor("#111827")
    styles["Heading2"].fontSize = 10
    styles["Heading2"].textColor = colors.HexColor("#1f2937")

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="RedMMOTitan Developer Handoff",
        author="RedMMOTitan handoff",
    )
    story = []
    story.append(Paragraph("RedMMOTitan — Developer Handoff PDF", styles["Title"]))
    story.append(
        Paragraph(
            md_inline(
                "Generated 2026-08-07. **PPG/PlanetGen not required** for fundamentals "
                "(`TitanFundamentals.uproject` + ThirdPersonMap). "
                "**Private GitHub:** invite developer by username. "
                "Full markdown lives beside this PDF in `Docs/DeveloperHandoff/`."
            ),
            styles["Body"],
        )
    )
    story.append(Spacer(1, 10))

    for idx, path in enumerate(SOURCES):
        if not path.exists():
            continue
        if idx:
            story.append(PageBreak())
        story.extend(md_to_flowables(path.read_text(encoding="utf-8"), styles))

    doc.build(story)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
