"""The CV as a PDF, read back with a text extractor. No database; nothing may be written to disk."""
import io

import pytest
from pypdf import PdfReader

import cvpdf
import cvprint
from cvsample import BLOCKS, content, missing_or_out_of_order, pdf_pages, pdf_text, pieces
from files import forbid_disk_writes

WHO = {"title": "Zarvin Quillfeather CV", "author": "Zarvin Quillfeather"}
FILLER = "Wrote a weekly report on depot delays for the regional managers and presented the findings every Monday morning."


def render(blocks):
    return cvpdf.render(blocks, **WHO)


def test_pdf_text_comes_back_in_block_order():
    data, pages = render(BLOCKS)
    assert data[:5] == b"%PDF-" and pages == 1
    assert missing_or_out_of_order(pieces(BLOCKS), pdf_text(data)) == []


def test_it_is_real_text_in_an_embedded_font_not_a_picture():
    reader = PdfReader(io.BytesIO(render(BLOCKS)[0]))
    resources = reader.pages[0]["/Resources"]
    assert "/Font" in resources and "/XObject" not in resources
    assert all("LiberationSans" in str(font.get_object().get("/BaseFont")) for font in resources["/Font"].values())


@pytest.mark.parametrize("text", ["Nguyễn Thị Çağla Łukasz-O'Brien", "Московский государственный университет", "Ελληνικά (Basic)",
                                  "Saved £120,000 and €5,000 a year", "Smith & Sons <Zzqx> “quoted” – dash … and 50% more"])
def test_accents_other_alphabets_and_a_pound_sign_survive(text):
    assert cvpdf.unsupported(text) == ""
    assert text in pdf_text(render([("name", text), ("line", text), ("bullet", text)])[0])


def test_unsupported_names_each_missing_character_once():
    assert cvpdf.unsupported("Paid ₹5 lakh, 中文 😀 שלום then ₹9 中") == "₹中文😀שלום"
    assert cvpdf.unsupported("Plain text, José, Łukasz and £5") == ""
    assert cvpdf.unsupported("zero‍width and a selector️, a tab\tand a break\n") == ""
    assert cvpdf.unsupported("") == ""


def test_what_the_font_cannot_draw_prints_as_a_question_mark():
    data, _ = render([("line", "Paid ₹5 lakh at 中文 Ltd"), ("bullet", "Kept the rest: £5 and José")])
    text = pdf_text(data)
    assert "Paid ?5 lakh at ?? Ltd" in text and "Kept the rest: £5 and José" in text


def test_page_count_grows_with_content():
    assert render(BLOCKS)[1] == 1
    long = BLOCKS + [("bullet", f"{FILLER} ({n})") for n in range(150)]
    data, pages = render(long)
    assert pages >= 3 and pages == len(PdfReader(io.BytesIO(data)).pages)
    assert missing_or_out_of_order(pieces(long), pdf_text(data)) == []


def test_hiding_a_bullet_can_bring_the_count_back_down():
    c = content()
    c["work"][0]["bullets"] = [{"text": f"{FILLER} ({n})", "achievement_id": "", "hidden": False} for n in range(12)] * 4
    over = render(cvprint.blocks(c))[1]
    for bullet in c["work"][0]["bullets"][6:]:
        bullet["hidden"] = True
    assert over >= 2 and render(cvprint.blocks(c))[1] == 1


def test_a_heading_is_not_left_at_the_foot_of_a_page():
    for filler in range(40, 64):  # somewhere in this range the heading reaches the foot of the first page
        blocks = [("line", f"Filler line {n}") for n in range(filler)] + [
            ("heading", "Work experience"), ("entry", "Zzqx Holdings Ltd, Pune, India", "Jul 2023 to Aug 2025"), ("sub", "Data Analyst"),
            ("bullet", "Built a weekly delays report")]
        pages = pdf_pages(render(blocks)[0])
        with_heading = next(text for text in pages if "Work experience" in text)
        assert "Zzqx Holdings Ltd" in with_heading and "Data Analyst" in with_heading, filler
    assert len(pages) == 2  # the range did cross a page boundary


def test_dates_sit_on_the_first_line_of_a_long_employer_name():
    long_name = "The Zzqx Institute for Applied Logistics, Transport Planning and Regional Economic Development, Bengaluru, India"
    text = pdf_text(render([("entry", long_name, "Jul 2023 to Aug 2025"), ("sub", "Data Analyst")])[0])
    assert missing_or_out_of_order([long_name, "Jul 2023 to Aug 2025", "Data Analyst"], text) == []


def test_a_long_unbroken_address_does_not_fail():
    address = "github.com/" + "zzqx" * 60
    data, pages = render([("line", address), ("bullet", address), ("entry", address, "Jul 2023 to Aug 2025")])
    assert pages == 1 and pdf_text(data).replace(" ", "").count("zzqx" * 60) == 3


def test_empty_blocks_and_blank_text_are_skipped():
    data, pages = render([("line", ""), ("bullet", "  "), ("entry", "", "Jul 2023"), ("gap", ""), ("line", "Only this")])
    assert pages == 1 and pdf_text(data) == "Only this"
    assert render([])[1] == 1


def test_title_and_author_are_set_and_no_file_is_written(monkeypatch):
    forbid_disk_writes(monkeypatch)
    data, _ = render(BLOCKS)
    meta = PdfReader(io.BytesIO(data)).metadata
    assert meta.title == "Zarvin Quillfeather CV" and meta.author == "Zarvin Quillfeather"


def test_the_letter_prints_as_one_page_in_order():
    from datetime import date
    letter = cvprint.letter_blocks(content(), "Ms Patel", date(2026, 10, 13))
    data, pages = cvpdf.render(letter, title="Zarvin Quillfeather cover letter", author="Zarvin Quillfeather")
    assert pages == 1 and missing_or_out_of_order(pieces(letter), pdf_text(data)) == []
