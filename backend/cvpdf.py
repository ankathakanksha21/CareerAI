"""Print blocks (see cvprint) to a PDF, in memory, and the number of pages it runs to.

The text is real text in reading order, set in Liberation Sans, which has the letter widths of
Arial, so lines break where they do in the Word file. The font is bundled (backend/fonts, SIL Open
Font Licence) and only the characters used are embedded. It has no Arabic, Hindi, Chinese,
Japanese, Korean or Thai letters and no rupee sign, and it cannot lay out right-to-left text:
`unsupported` names such characters so the page can say so, and they print as "?".

Nothing is written to disk."""
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont
from fpdf import FPDF

import cvprint as page

FONTS = Path(__file__).parent / "fonts"
REGULAR, BOLD = FONTS / "LiberationSans-Regular.ttf", FONTS / "LiberationSans-Bold.ttf"
FAMILY = "cv"
MM = 72 / 25.4            # points in a millimetre
BULLET = "•"
RIGHT_TO_LEFT = ("R", "AL", "AN")
DATE_GAP_PT = 10          # between an employer's name and its dates
RULE_PT = 0.5             # the line under a section heading
# The page count shown in the app is this file's, so it has to be Word's too. The type, margins and
# spacing are the same in both writers; what is left is where a page breaks. Word keeps a heading with
# what follows it and never leaves one line of a paragraph alone, so the same is done here. Checked
# against Word itself with scripts/page_check.py: run it again after any change to the layout.
LINE_PT = page.BODY_PT * page.LINE_HEIGHT
KEEP_LINES = 3            # a heading or an entry is never left with fewer lines than this below it on its page
WHOLE_LINES = 3           # a paragraph of up to this many lines is never split across pages

# the libraries log what they could not draw, and that is the user's text: only real errors are kept
for noisy in ("fpdf", "fontTools"):
    logging.getLogger(noisy).setLevel(logging.ERROR)


@lru_cache(maxsize=1)
def _characters() -> frozenset:
    """Every character both weights of the font can draw."""
    return frozenset(TTFont(REGULAR, lazy=True).getBestCmap()) & frozenset(TTFont(BOLD, lazy=True).getBestCmap())


def _invisible(ch: str) -> bool:
    """A character with nothing to draw: a zero-width joiner, a variation selector."""
    return unicodedata.category(ch) == "Cf" or "︀" <= ch <= "️"


def _drawable(ch: str) -> bool:
    return ch.isspace() or (ord(ch) in _characters() and unicodedata.bidirectional(ch) not in RIGHT_TO_LEFT)


def unsupported(text: str) -> str:
    """The characters in the text that the PDF cannot show, each once, in the order met."""
    missing = []
    for ch in page.clean(text):
        if not _invisible(ch) and not _drawable(ch) and ch not in missing:
            missing.append(ch)
    return "".join(missing)


def _safe(text: str) -> str:
    """The text as the PDF prints it: a character the font cannot draw becomes a question mark."""
    return "".join(ch if _drawable(ch) else "?" for ch in page.clean(text) if not _invisible(ch))


def render(blocks: list[tuple], *, title: str, author: str) -> tuple[bytes, int]:
    """The blocks as an A4 PDF, and how many pages it has."""
    pdf = FPDF(format="A4", unit="pt")
    pdf.set_margins(page.MARGIN_X_MM * MM, page.MARGIN_Y_MM * MM, page.MARGIN_X_MM * MM)
    pdf.set_auto_page_break(True, margin=page.MARGIN_Y_MM * MM)
    pdf.add_font(FAMILY, "", str(REGULAR))
    pdf.add_font(FAMILY, "B", str(BOLD))
    pdf.set_title(_safe(title))
    pdf.set_author(_safe(author))
    pdf.set_creator("UK Career Navigator")
    pdf.set_line_width(RULE_PT)
    pdf.add_page()
    width = pdf.epw

    def font(bold: bool = False, size: float = page.BODY_PT) -> None:
        pdf.set_font(FAMILY, "B" if bold else "", size)

    def keep(points: float) -> None:
        """Start a new page now if what follows would not fit on this one."""
        if pdf.will_page_break(points):
            pdf.add_page()

    def together(text: str, indent: float = 0) -> None:
        """As Word does, never leave one line of a paragraph alone at the foot of a page: a short
        paragraph moves over whole, a longer one keeps at least two lines here."""
        font()
        lines = len(pdf.multi_cell(width - indent, LINE_PT, text, align="L", dry_run=True, output="LINES"))
        keep(LINE_PT * (lines if lines <= WHOLE_LINES else 2))

    def write(text: str, *, bold: bool = False, size: float = page.BODY_PT, indent: float = 0) -> None:
        font(bold, size)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(width - indent, size * page.LINE_HEIGHT, text, align="L", new_x="LMARGIN", new_y="NEXT")

    for block in blocks:
        kind, text = block[0], _safe(block[1])
        if kind == "gap":
            pdf.ln(LINE_PT)
        elif not text:
            continue
        elif kind == "name":
            write(text, bold=True, size=page.NAME_PT)
        elif kind == "heading":
            keep(page.HEADING_BEFORE_PT + page.HEADING_PT * page.LINE_HEIGHT + page.HEADING_AFTER_PT + page.ENTRY_BEFORE_PT + KEEP_LINES * LINE_PT)
            pdf.ln(page.HEADING_BEFORE_PT)
            write(text, bold=True, size=page.HEADING_PT)
            pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + width, pdf.get_y() + 1)
            pdf.ln(page.HEADING_AFTER_PT)
        elif kind == "entry":
            keep(page.ENTRY_BEFORE_PT + KEEP_LINES * LINE_PT)
            pdf.ln(page.ENTRY_BEFORE_PT)
            dates = _safe(block[2]) if len(block) > 2 else ""
            font()
            room = pdf.get_string_width(dates) + DATE_GAP_PT if dates else 0
            top = pdf.get_y()
            font(bold=True)
            pdf.multi_cell(width - room, LINE_PT, text, align="L", new_x="LMARGIN", new_y="NEXT")
            if dates:  # at the right margin, level with the first line of the name
                below = pdf.get_y()
                font()
                pdf.set_xy(pdf.l_margin + width - room, top)
                pdf.cell(room, LINE_PT, dates, align="R")
                pdf.set_xy(pdf.l_margin, below)
        elif kind == "sub":
            write(text, bold=True)
        elif kind == "bullet":
            together(text, page.BULLET_INDENT_PT)
            pdf.cell(page.BULLET_INDENT_PT, LINE_PT, BULLET)
            write(text, indent=page.BULLET_INDENT_PT)
        elif kind == "para":
            together(text)
            write(text)
            pdf.ln(page.PARA_AFTER_PT)
        else:  # contact, line
            together(text)
            write(text)
    return bytes(pdf.output()), pdf.page_no()
