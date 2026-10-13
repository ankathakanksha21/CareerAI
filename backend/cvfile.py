"""A CV file to plain text, entirely in memory. The bytes are read and dropped: nothing here
writes to disk, and only the text goes any further.

What kind of file it is comes from its first bytes, never from its name. Every file that
cannot be used raises Unreadable with a message written for the person who uploaded it."""
import io
import re
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader

MAX_BYTES = 4 * 1024 * 1024      # Vercel refuses a request body over 4.5 MB
MAX_CHARS = 30_000               # the same cap as pasted text
MIN_CHARS = 100                  # fewer non-space characters than this is a scan, not a CV
MAX_PAGES = 20
MAX_UNPACKED = 20 * 1024 * 1024  # a Word file whose text parts unpack beyond this is not a CV

EMPTY = "That file is empty."
TOO_BIG = "That file is over 4 MB. Upload a smaller one, or paste the text instead."
WRONG_TYPE = "Upload a PDF or a Word (.docx) file."
LOCKED = "This PDF is password-protected. Remove the password, or paste the text instead."
BROKEN = "We could not open that file. Save it again as PDF or .docx, or paste the text instead."
NO_TEXT = "We could not read any text in this file. Paste the text instead."

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Word stores every text box twice: the real one, and this older copy for programs that cannot read it
FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
HEADER = re.compile(r"word/header\d*\.xml")
# Characters a database text column refuses or that mean nothing on screen: control characters,
# the "unknown character" mark Word's bullets become, private-use symbols, half of a surrogate pair
_JUNK = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f�-\ud800-\udfff]")


class Unreadable(Exception):
    """This file cannot be used. str() is the message shown to the user."""


def clean(text: str) -> str:
    text = _JUNK.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _pdf(data: bytes) -> tuple[str, bool]:
    """The text of the first pages, and whether pages were left unread."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):  # many PDFs are locked against editing only
            raise Unreadable(LOCKED)
        pages = reader.pages
        parts, size = [], 0
        for page in pages[:MAX_PAGES]:
            parts.append((page.extract_text() or "").strip())
            size += len(parts[-1])
            if size > MAX_CHARS:
                break
        return "\n".join(parts), len(pages) > MAX_PAGES
    except Unreadable:
        raise
    except Exception:  # a damaged PDF fails inside pypdf in many different ways; all of them mean the same to the user
        raise Unreadable(BROKEN) from None


def _paragraphs(root) -> list[str]:
    """The text of every paragraph in document order: body, table cells and text boxes."""
    found = []

    def own_text(paragraph) -> str:
        parts = []

        def collect(node):
            for child in node:
                if child.tag in (W + "p", FALLBACK):  # a paragraph nested in this one (a text box) is listed on its own
                    continue
                if child.tag == W + "t":
                    parts.append(child.text or "")
                elif child.tag == W + "tab":
                    parts.append(" ")
                elif child.tag in (W + "br", W + "cr"):
                    parts.append("\n")
                else:
                    collect(child)
        collect(paragraph)
        return "".join(parts)

    def visit(node):
        for child in node:
            if child.tag == FALLBACK:
                continue
            if child.tag == W + "p":
                found.append(own_text(child))
            visit(child)
    visit(root)
    return found


def _docx(data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = archive.namelist()
    except Exception:
        raise Unreadable(BROKEN) from None
    if "word/document.xml" not in names:
        raise Unreadable(WRONG_TYPE)  # a spreadsheet, a presentation or any other zip
    headers = sorted(n for n in names if HEADER.fullmatch(n))
    if sum(archive.getinfo(n).file_size for n in [*headers, "word/document.xml"]) > MAX_UNPACKED:
        raise Unreadable(BROKEN)
    try:
        top, body = [], []
        for name in [*headers, "word/document.xml"]:
            xml = archive.read(name)
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:  # a real Word file never declares entities
                raise Unreadable(BROKEN)
            (body if name == "word/document.xml" else top).extend(_paragraphs(ElementTree.fromstring(xml)))
    except Unreadable:
        raise
    except Exception:  # bad compression, an encrypted part, malformed or absurdly nested XML
        raise Unreadable(BROKEN) from None
    # the first-page, odd-page and even-page headers usually repeat the same name and contact line
    return "\n".join([*dict.fromkeys(top), *body])


def text(data: bytes) -> tuple[str, bool]:
    """The plain text of a PDF or Word CV, and whether some of it was left out for length."""
    if not data:
        raise Unreadable(EMPTY)
    if len(data) > MAX_BYTES:
        raise Unreadable(TOO_BIG)
    if data.startswith(b"%PDF-"):
        raw, more = _pdf(data)
    elif data.startswith(b"PK\x03\x04"):
        raw, more = _docx(data), False
    else:
        raise Unreadable(WRONG_TYPE)
    cleaned = clean(raw)
    if len(re.sub(r"\s", "", cleaned)) < MIN_CHARS:
        raise Unreadable(NO_TEXT)
    return cleaned[:MAX_CHARS], more or len(cleaned) > MAX_CHARS
