"""Real PDF and Word files built in memory for tests. Nothing here touches the disk, and the
people and employers in them cannot be real."""
import io
import zipfile
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAMESPACES = (f'xmlns:w="{W}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
              'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" xmlns:v="urn:schemas-microsoft-com:vml"')

CV_LINES = [
    "Zarvin Quillfeather",
    "Systems Engineer, Zzqx Holdings Ltd, Pune, India, Jul 2023 - Aug 2025",
    "Built a weekly delivery delays report in SQL and Excel used by 15 depot managers.",
    "Wrote a Python script that merged three spreadsheets, saving around 5 hours a week.",
    "BTech Computer Science, University of Zzqx, India, Jul 2019 - May 2023, CGPA 8.4/10",
    "Skills: Python, SQL, Excel, Power BI. Languages: English (fluent), Hindi (native).",
]


def pdf(pages: list[list[str]]) -> bytes:
    """A valid PDF with one text stream per page; each string is one line of the page."""
    def line(text: str) -> bytes:
        return b"(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1") + b") Tj T*"

    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
               2: f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(len(pages)))}] /Count {len(pages)} >>".encode(),
               3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    for i, lines in enumerate(pages):
        stream = b"BT /F1 11 Tf 50 780 Td 14 TL " + b" ".join(line(x) for x in lines) + b" ET"
        objects[4 + 2 * i] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                              f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>").encode()
        objects[5 + 2 * i] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out, offsets = b"%PDF-1.4\n", {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offsets[n] for n in sorted(objects))
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def locked_pdf(user_password: str, pages=None) -> bytes:
    """The same PDF, encrypted. An empty user password is a file anyone can open but not change."""
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf(pages or [CV_LINES]))))
    writer.encrypt(user_password=user_password, owner_password="owner-only")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def table(*cells: list[str]) -> str:
    """One table row; each cell is a list of paragraphs."""
    return "<w:tbl><w:tr>" + "".join(f"<w:tc>{''.join(paragraph(p) for p in cell)}</w:tc>" for cell in cells) + "</w:tr></w:tbl>"


def text_box(text: str) -> str:
    """How Word stores a text box: the real one, and an older copy of it for programs that cannot read the first."""
    inner = f"<w:txbxContent>{paragraph(text)}</w:txbxContent>"
    return ("<w:p><w:r><mc:AlternateContent>"
            f'<mc:Choice Requires="wps"><w:drawing><wps:txbx>{inner}</wps:txbx></w:drawing></mc:Choice>'
            f"<mc:Fallback><w:pict><v:textbox>{inner}</v:textbox></w:pict></mc:Fallback>"
            "</mc:AlternateContent></w:r></w:p>")


def docx(body: str, headers: tuple = (), prolog: str = "") -> bytes:
    """A Word file holding the given body XML, with one header part per entry in `headers`."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?>{prolog}<w:document {NAMESPACES}><w:body>{body}</w:body></w:document>')
        for i, text in enumerate(headers, start=1):
            z.writestr(f"word/header{i}.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:hdr {NAMESPACES}>{paragraph(text)}</w:hdr>')
    return out.getvalue()


def cv_pdf() -> bytes:
    return pdf([CV_LINES])


def cv_docx() -> bytes:
    return docx("".join(paragraph(x) for x in CV_LINES))
