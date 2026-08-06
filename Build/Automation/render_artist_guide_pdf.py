from docx import Document
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph as RParagraph, Spacer, PageBreak, Table, TableStyle, KeepTogether


DOCX = r"D:\RedMMOTitanWindowsData\ArtistHandoff\RED_Mars_27_Patches_Artist_Guide_UA.docx"
PDF = r"D:\RedMMOTitanWindowsData\ArtistHandoff\RED_Mars_27_Patches_Artist_Guide_UA.pdf"

pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", r"C:\Windows\Fonts\ariali.ttf"))

NAVY = colors.HexColor("#14304B")
BLUE = colors.HexColor("#237AAA")
ORANGE = colors.HexColor("#C45B2B")
MUTED = colors.HexColor("#5A646E")

styles = getSampleStyleSheet()
body = ParagraphStyle("UA Body", parent=styles["BodyText"], fontName="Arial", fontSize=10.3, leading=13.2, spaceAfter=6, textColor=colors.HexColor("#20252A"))
h1 = ParagraphStyle("UA H1", parent=body, fontName="Arial-Bold", fontSize=15.5, leading=18.5, textColor=NAVY, spaceBefore=14, spaceAfter=7, keepWithNext=True)
h2 = ParagraphStyle("UA H2", parent=body, fontName="Arial-Bold", fontSize=12.5, leading=15, textColor=BLUE, spaceBefore=10, spaceAfter=5, keepWithNext=True)
bullet = ParagraphStyle("UA Bullet", parent=body, leftIndent=18, firstLineIndent=-10, bulletIndent=5, spaceAfter=4)
cover_title = ParagraphStyle("Cover", parent=body, fontName="Arial-Bold", fontSize=27, leading=31, alignment=TA_CENTER, textColor=NAVY, spaceBefore=120, spaceAfter=10)
cover_sub = ParagraphStyle("CoverSub", parent=body, fontSize=14, leading=18, alignment=TA_CENTER, textColor=BLUE, spaceAfter=24)


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(letter[0] - 0.72 * inch, letter[1] - 0.45 * inch, "RED MMO | Planet Surface Artist Handoff")
    canvas.drawCentredString(letter[0] / 2, 0.42 * inch, f"Марс після початку тераформування | UE 5.8 | {doc.page}")
    canvas.restoreState()


pdf = BaseDocTemplate(PDF, pagesize=letter, leftMargin=0.78*inch, rightMargin=0.78*inch, topMargin=0.68*inch, bottomMargin=0.68*inch)
frame = Frame(pdf.leftMargin, pdf.bottomMargin, pdf.width, pdf.height, id="main")
pdf.addPageTemplates(PageTemplate(id="all", frames=[frame], onPage=page))

source = Document(DOCX)
story = []
cover_index = 0
number = 0

for child in source.element.body.iterchildren():
    if isinstance(child, CT_P):
        p = Paragraph(child, source)
        text = p.text.strip()
        has_page_break = bool(p._p.xpath('.//w:br[@w:type="page"]'))
        if text:
            style_name = p.style.name if p.style else "Normal"
            if cover_index == 0:
                story.append(RParagraph(esc(text), cover_title)); cover_index += 1
            elif cover_index == 1:
                story.append(RParagraph(esc(text), cover_sub)); cover_index += 1
            elif style_name.startswith("Heading 1"):
                story.append(RParagraph(esc(text), h1))
            elif style_name.startswith("Heading 2") or style_name.startswith("Heading 3"):
                story.append(RParagraph(esc(text), h2))
            elif style_name.startswith("List Number"):
                number += 1
                story.append(RParagraph(esc(text), bullet, bulletText=f"{number}."))
            elif style_name.startswith("List Bullet"):
                number = 0
                story.append(RParagraph(esc(text), bullet, bulletText="•"))
            else:
                number = 0
                story.append(RParagraph(esc(text), body))
        if has_page_break:
            story.append(PageBreak())
    elif isinstance(child, CT_Tbl):
        table = DocxTable(child, source)
        data = []
        header_cell = ParagraphStyle("TableHeader", parent=body, textColor=colors.white, fontName="Arial-Bold")
        for row_index, row in enumerate(table.rows):
            cell_style = header_cell if row_index == 0 and len(row.cells) > 1 else body
            data.append([RParagraph(esc(cell.text.strip()), cell_style) for cell in row.cells])
        if not data:
            continue
        cols = len(data[0])
        widths = [pdf.width / cols] * cols
        rt = Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
        ts = [
            ("FONTNAME", (0,0), (-1,-1), "Arial"),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 7),
            ("RIGHTPADDING", (0,0), (-1,-1), 7),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#AAB8C2")),
        ]
        if cols > 1:
            ts += [("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Arial-Bold")]
            for r in range(2, len(data), 2):
                ts.append(("BACKGROUND", (0,r), (-1,r), colors.HexColor("#F2F6F8")))
        else:
            ts += [("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#E8F4F7")), ("BOX", (0,0), (-1,-1), 1.0, BLUE)]
        rt.setStyle(TableStyle(ts))
        story.extend([Spacer(1, 4), rt, Spacer(1, 8)])

pdf.build(story)
print(PDF)
