import builtins
import io
import tempfile
import zipfile

import pytest

import cvfile
from files import CV_LINES, cv_docx, cv_pdf, docx, locked_pdf, paragraph, pdf, table, text_box

LONG_LINE = "Analysed delivery records for the operations team every single week. "  # about 70 characters


def refused(data: bytes) -> str:
    with pytest.raises(cvfile.Unreadable) as e:
        cvfile.text(data)
    return str(e.value)


# ---------- files that read ----------

@pytest.mark.parametrize("make", [cv_pdf, cv_docx])
def test_a_cv_comes_back_as_its_lines_in_order(make):
    text, cut = cvfile.text(make())
    assert text.split("\n") == CV_LINES
    assert cut is False


def test_a_pdf_of_several_pages_is_read_through():
    text, _ = cvfile.text(pdf([CV_LINES[:3], CV_LINES[3:]]))
    assert text.split("\n") == CV_LINES


def test_word_tables_are_read_cell_by_cell():
    body = table(["SKILLS", "Python"], ["EXPERIENCE", CV_LINES[1], CV_LINES[2]]) + paragraph(CV_LINES[4])
    text, _ = cvfile.text(docx(body))
    assert text.split("\n") == ["SKILLS", "Python", "EXPERIENCE", CV_LINES[1], CV_LINES[2], CV_LINES[4]]


def test_the_page_header_of_a_word_file_is_read_once():
    # Word keeps a header part for the first page, odd pages and even pages, often with the same text
    text, _ = cvfile.text(docx("".join(paragraph(x) for x in CV_LINES[1:]), headers=(CV_LINES[0], CV_LINES[0], CV_LINES[0])))
    assert text.split("\n") == CV_LINES


def test_a_text_box_is_read_once_not_twice():
    text, _ = cvfile.text(docx(paragraph(CV_LINES[1]) + text_box("Boxed profile for Zarvin") + "".join(paragraph(x) for x in CV_LINES[2:])))
    assert text.count("Boxed profile for Zarvin") == 1
    assert text.index(CV_LINES[1]) < text.index("Boxed profile") < text.index(CV_LINES[2])


def test_tabs_and_line_breaks_inside_a_paragraph():
    body = "<w:p><w:r><w:t>Systems Engineer</w:t><w:tab/><w:t>Jul 2023 - Aug 2025</w:t><w:br/><w:t>Zzqx Holdings Ltd</w:t></w:r></w:p>"
    text, _ = cvfile.text(docx(body + "".join(paragraph(x) for x in CV_LINES[2:])))
    assert text.split("\n")[:2] == ["Systems Engineer Jul 2023 - Aug 2025", "Zzqx Holdings Ltd"]


def test_a_pdf_anyone_can_open_is_read_even_though_it_is_encrypted():
    text, _ = cvfile.text(locked_pdf(""))
    assert text.split("\n") == CV_LINES


# ---------- limits ----------

def test_only_the_first_pages_of_a_very_long_pdf_are_read():
    pages = [[f"This is page number {n} of a very long document."] + CV_LINES for n in range(1, 301)]
    text, cut = cvfile.text(pdf(pages))
    assert f"page number {cvfile.MAX_PAGES} of" in text and f"page number {cvfile.MAX_PAGES + 1} of" not in text
    assert cut is True


def test_long_text_is_cut_and_says_so():
    text, cut = cvfile.text(pdf([[LONG_LINE] * 50 for _ in range(15)]))  # about 52,000 characters
    assert len(text) == cvfile.MAX_CHARS and cut is True
    text, cut = cvfile.text(docx("".join(paragraph(LONG_LINE) for _ in range(600))))
    assert len(text) <= cvfile.MAX_CHARS and cut is True


def test_text_the_database_cannot_store_is_removed():
    assert cvfile.clean("Built\x00 a re\x07port� for 15 managers\ud83d") == "Built a report for 15 managers"
    assert cvfile.clean("one  \t two\xa0three \r\n\r\n\r\n\r\n four ") == "one two three\n\nfour"


# ---------- files that are refused, each with a plain message ----------

def test_an_empty_file():
    assert refused(b"") == "That file is empty."


def test_a_file_over_the_limit_is_refused_before_it_is_opened(monkeypatch):
    monkeypatch.setattr(cvfile, "_pdf", lambda data: pytest.fail("opened"))
    assert refused(b"%PDF-1.4\n" + b"0" * cvfile.MAX_BYTES) == "That file is over 4 MB. Upload a smaller one, or paste the text instead."


@pytest.mark.parametrize("data", [
    b"Zarvin Quillfeather. Systems Engineer at Zzqx Holdings Ltd. " * 10,   # a text file renamed .pdf
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600,                    # an old .doc
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 600,                                   # a picture
])
def test_a_file_that_is_neither_type_whatever_it_is_called(data):
    assert refused(data) == "Upload a PDF or a Word (.docx) file."


def test_a_zip_that_is_not_a_word_file():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("xl/workbook.xml", "<workbook/>")
    assert refused(out.getvalue()) == "Upload a PDF or a Word (.docx) file."


def test_a_scanned_pdf_has_no_text():
    assert refused(pdf([[]])) == "We could not read any text in this file. Paste the text instead."
    assert refused(pdf([["Page 1"]])) == "We could not read any text in this file. Paste the text instead."


def test_a_word_file_with_almost_nothing_in_it():
    assert refused(docx(paragraph("CV"))) == "We could not read any text in this file. Paste the text instead."


def test_a_password_protected_pdf():
    assert refused(locked_pdf("secret")) == "This PDF is password-protected. Remove the password, or paste the text instead."


@pytest.mark.parametrize("data", [b"%PDF-1.4\nthis is not really a pdf at all " * 20, b"PK\x03\x04" + b"not a zip " * 60,
                                  cv_pdf()[:200], cv_docx()[:-40]])
def test_a_damaged_file(data):
    assert refused(data) == "We could not open that file. Save it again as PDF or .docx, or paste the text instead."


def test_a_word_file_that_declares_entities_is_refused():
    hostile = docx("".join(paragraph(x) for x in CV_LINES), prolog='<!DOCTYPE d [<!ENTITY a "aaaaaaaaaa">]>')
    assert refused(hostile) == "We could not open that file. Save it again as PDF or .docx, or paste the text instead."


def test_a_word_file_that_unpacks_too_large_is_refused_without_being_unpacked(monkeypatch):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b" " * (cvfile.MAX_UNPACKED + 1))  # a few kilobytes once compressed
    data = out.getvalue()
    assert len(data) < 100_000
    monkeypatch.setattr(zipfile.ZipFile, "read", lambda *a, **k: pytest.fail("unpacked"))
    assert refused(data) == "We could not open that file. Save it again as PDF or .docx, or paste the text instead."


# ---------- the file never reaches the disk ----------

@pytest.mark.parametrize("make", [cv_pdf, cv_docx])
def test_reading_a_file_never_touches_the_disk(monkeypatch, make):
    data = make()
    cvfile.text(data)  # first, so that anything Python loads lazily is already loaded

    def no_disk(*args, **kwargs):
        raise AssertionError("the file was written to disk")
    for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, no_disk)
    monkeypatch.setattr(builtins, "open", no_disk)
    monkeypatch.setattr(io, "open", no_disk)
    assert cvfile.text(data)[0].split("\n") == CV_LINES
