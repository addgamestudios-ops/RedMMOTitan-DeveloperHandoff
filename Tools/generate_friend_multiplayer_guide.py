from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "RedMMOTitan_Friend_Multiplayer_Quickstart.pdf"

INK = colors.HexColor("#EAF4FF")
MUTED = colors.HexColor("#9CB2C9")
CYAN = colors.HexColor("#31D7FF")
GOLD = colors.HexColor("#FFCB4B")
PANEL = colors.HexColor("#14243A")
PANEL_2 = colors.HexColor("#0D192B")
BG = colors.HexColor("#07111F")
RED = colors.HexColor("#FF655E")


class GuideDoc(BaseDocTemplate):
    def __init__(self, filename: Path):
        super().__init__(
            str(filename),
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=18 * mm,
            bottomMargin=16 * mm,
            title="Red MMO Titan - Friend Multiplayer Quickstart",
            author="Red MMO Titan Windows Build",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="guide", frames=[frame], onPage=self.draw_page))

    def draw_page(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BG)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.setFillColor(CYAN)
        canvas.rect(0, A4[1] - 7 * mm, A4[0], 7 * mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#03101B"))
        canvas.drawString(16 * mm, A4[1] - 4.7 * mm, "RED MMO TITAN  /  WINDOWS MULTIPLAYER TEST BUILD")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 8 * mm, "Steam development App ID 480  |  Updated 13 July 2026")
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()


styles = getSampleStyleSheet()
title = ParagraphStyle(
    "Title",
    parent=styles["Title"],
    fontName="Helvetica-Bold",
    fontSize=26,
    leading=29,
    textColor=INK,
    alignment=TA_CENTER,
    spaceAfter=5 * mm,
)
subtitle = ParagraphStyle(
    "Subtitle",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=11,
    leading=15,
    textColor=MUTED,
    alignment=TA_CENTER,
    spaceAfter=7 * mm,
)
heading = ParagraphStyle(
    "Heading",
    parent=styles["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=14,
    leading=17,
    textColor=CYAN,
    spaceBefore=4 * mm,
    spaceAfter=2.5 * mm,
)
body = ParagraphStyle(
    "Body",
    parent=styles["BodyText"],
    fontName="Helvetica",
    fontSize=9.4,
    leading=13.2,
    textColor=INK,
    spaceAfter=2.3 * mm,
)
small = ParagraphStyle(
    "Small",
    parent=body,
    fontSize=8.4,
    leading=11.6,
    textColor=MUTED,
)
step_number = ParagraphStyle(
    "StepNumber",
    parent=body,
    fontName="Helvetica-Bold",
    fontSize=18,
    leading=19,
    textColor=GOLD,
    alignment=TA_CENTER,
)
step_text = ParagraphStyle(
    "StepText",
    parent=body,
    fontSize=9,
    leading=12.3,
    spaceAfter=0,
)
warning = ParagraphStyle(
    "Warning",
    parent=body,
    fontSize=9,
    leading=12.4,
    textColor=colors.HexColor("#FFF1C0"),
    spaceAfter=0,
)


def p(text, style=body):
    return Paragraph(text, style)


def panel(rows, widths=None, background=PANEL):
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#274766")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#274766")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def step(n, label, text):
    return [p(str(n), step_number), p(f"<b>{label}</b><br/>{text}", step_text)]


def build_story():
    story = [
        Spacer(1, 4 * mm),
        p("FRIEND MULTIPLAYER QUICKSTART", title),
        p(
            "Use one identical packaged Windows build on two different Steam accounts. "
            "No Unreal Engine installation is needed on your friend's PC.",
            subtitle,
        ),
        panel(
            [[p("SEND THIS", step_number), p("Send the complete <b>RedMMOTitan_Friend_PvP</b> archive. Your friend must extract the whole folder before launching Titan.exe. Do not run it from inside the ZIP.", warning)]],
            [34 * mm, 140 * mm],
            PANEL_2,
        ),
        p("Before both players launch", heading),
        panel(
            [
                step(1, "Use separate accounts", "Steam must be open, signed in, and Online on both PCs. Use two different Steam accounts."),
                step(2, "Install the same build", "Extract the exact same ZIP to a normal local folder with at least 5 GB free."),
                step(3, "Launch the game", "Run Titan.exe while Steam stays open. Allow Titan through the normal Windows Firewall prompt if it appears."),
            ],
            [18 * mm, 156 * mm],
        ),
        p("Host the lobby", heading),
        panel(
            [
                step(1, "Open multiplayer", "Press F8 in the packaged game, or press Escape and choose Multiplayer / Lobby."),
                step(2, "Create", "Click CREATE GAME and wait until the status reports that the RED multiplayer session is connected."),
                step(3, "Invite", "Click INVITE FRIENDS, choose your friend in Steam, and remain in the game while they connect."),
            ],
            [18 * mm, 156 * mm],
        ),
        p("Join the lobby", heading),
        panel(
            [
                step(1, "Preferred", "Accept the Steam invite while Titan is already running."),
                step(2, "Browser fallback", "Press F8, click FIND GAMES, select Red MMO Titan PvP, then click JOIN SELECTED."),
                step(3, "Retry once", "If no row appears, wait 10 seconds after the host finishes creating the game, then click FIND GAMES again."),
            ],
            [18 * mm, 156 * mm],
        ),
        Spacer(1, 4 * mm),
        p(
            "Important: do not add -nosteam to the launch command. Keep steam_appid.txt in the build exactly where it was supplied.",
            warning,
        ),
        PageBreak(),
        Spacer(1, 4 * mm),
        p("PLAY TOGETHER / TEST CONTROLS", title),
        p("A short two-player loop to verify combat, vehicles, death, and respawn.", subtitle),
        p("Core controls", heading),
        panel(
            [
                [p("ON FOOT", step_text), p("IN A CRAFT", step_text)],
                [
                    p("<b>B or V</b> - board the nearby craft you are looking at<br/><b>F</b> - direct mini-fighter shortcut<br/><b>1 / 2</b> - swap weapon<br/><b>Q / E</b> - abilities<br/><b>Tab</b> - ability loadout", body),
                    p("<b>V</b> - exit<br/><b>C</b> - first/third-person camera<br/><b>L</b> - landing assist<br/><b>LMB</b> - fire<br/><b>Shift</b> - boost", body),
                ],
            ],
            [87 * mm, 87 * mm],
        ),
        p("Suggested test", heading),
        panel(
            [
                step(1, "Meet", "Confirm that each player can see the other's movement, aim, jetpack, and weapon swap."),
                step(2, "Fight", "Damage each other, trigger weapon overheat/cooldown, die, ragdoll, and respawn."),
                step(3, "Use ships", "Board with B/V, change camera with C, fire, exit, and destroy a ship while the other player is piloting it."),
            ],
            [18 * mm, 156 * mm],
        ),
        p("Troubleshooting", heading),
        panel(
            [
                [p("NO LOBBY", step_text), p("Confirm separate Steam accounts, Online status, and the identical ZIP. Let the host finish CREATE GAME before the friend searches. Restart Steam and Titan on both PCs if needed.", small)],
                [p("NO INVITE OVERLAY", step_text), p("Use FIND GAMES / JOIN SELECTED. The browser is the reliable fallback.", small)],
                [p("STEAM UNAVAILABLE", step_text), p("Do not use -nosteam. Confirm steam_appid.txt is present. Start Steam first, then Titan.exe.", small)],
                [p("CONNECTION BLOCKED", step_text), p("Allow Titan through the normal Windows Firewall prompt on both PCs. Steam relay is enabled; manual router port forwarding should normally be unnecessary.", small)],
                [p("CAPTURE A LOG", step_text), p("Use Titan/Saved/Logs/Titan.log inside the extracted build. Do not share passwords, Steam Guard codes, or private credentials.", small)],
            ],
            [43 * mm, 131 * mm],
        ),
        p("What App ID 480 means", heading),
        panel(
            [[p("DEVELOPMENT TEST ONLY", step_text), p("App ID 480 is Steam's public Spacewar development identity. It can test Steam transport and RED lobby discovery, but it cannot install Red MMO Titan as its own Steam Library title. A real Library build still requires the Steamworks-assigned App ID, Win64 depot, branch, and tester entitlement.", warning)]],
            [43 * mm, 131 * mm],
            PANEL_2,
        ),
    ]
    return story


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    GuideDoc(OUTPUT).build(build_story())
    print(OUTPUT)


if __name__ == "__main__":
    main()
