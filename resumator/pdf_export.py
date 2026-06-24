from __future__ import annotations

from datetime import datetime
from typing import Iterable
import json
import os
from pathlib import Path
import textwrap
from xml.sax.saxutils import escape as xml_escape
import zipfile

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover - fallback is used without reportlab
    letter = None
    pdfmetrics = None
    TTFont = None
    canvas = None

try:
    from docx import Document
    from docx.shared import Inches, Pt
except ImportError:  # pragma: no cover - optional DOCX export
    Document = None
    Inches = None
    Pt = None


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT = 54
TOP = 735
BOTTOM = 58
LINE_HEIGHT = 14
BODY_FONT_SIZE = 10
APP_NAME = "Resumator 10.1"
DEVELOPER = "LEONARDO CARDOSO DE MELO TEIXEIRA MENDES - PROCURADOR FEDERAL / AGU"
DOCUMENT_TITLE = "RESUMO GERADO POR IA"
PROMPT_DOCUMENT_TITLE = "PROMPT PARA ENVIO À IA"


def export_response_pdf(
    output_path: Path,
    response_text: str,
    prompt_name: str | None = None,
    source_pdf: Path | Iterable[Path] | None = None,
) -> Path:
    lines = _prepare_lines(response_text, prompt_name, source_pdf)
    if canvas is not None:
        _export_with_reportlab(output_path, lines)
        return output_path

    pages = _paginate(lines)
    pdf_bytes = _build_pdf(pages)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return output_path


def export_response_docx(
    output_path: Path,
    response_text: str,
    prompt_name: str | None = None,
    source_pdf: Path | Iterable[Path] | None = None,
    document_title: str = DOCUMENT_TITLE,
) -> Path:
    if Document is None or Inches is None or Pt is None:
        _export_docx_fallback(output_path, response_text, prompt_name, source_pdf, document_title)
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()

    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)

    title = document.add_paragraph()
    title_run = title.add_run(document_title)
    title_run.bold = True
    title_run.font.size = Pt(14)

    for line in _metadata_lines(prompt_name, source_pdf):
        paragraph = document.add_paragraph()
        paragraph.add_run(line).italic = True

    document.add_paragraph("")

    text = response_text.strip() or "Sem resposta informada."
    for paragraph_text in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        document.add_paragraph(paragraph_text.strip() if paragraph_text.strip() else "")

    document.save(str(output_path))
    return output_path


def export_prompt_docx(
    output_path: Path,
    prompt_text: str,
    prompt_name: str | None = None,
    source_pdf: Path | Iterable[Path] | None = None,
) -> Path:
    return export_response_docx(
        output_path,
        prompt_text,
        prompt_name=prompt_name,
        source_pdf=source_pdf,
        document_title=PROMPT_DOCUMENT_TITLE,
    )


def _export_docx_fallback(
    output_path: Path,
    response_text: str,
    prompt_name: str | None,
    source_pdf: Path | Iterable[Path] | None,
    document_title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    paragraphs = [("title", document_title)]
    paragraphs.extend(("meta", line) for line in _metadata_lines(prompt_name, source_pdf))
    paragraphs.append(("body", ""))

    text = response_text.strip() or "Sem resposta informada."
    for paragraph_text in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        paragraphs.append(("body", paragraph_text.strip() if paragraph_text.strip() else ""))

    document_xml = _docx_document_xml(paragraphs)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _docx_content_types_xml())
        archive.writestr("_rels/.rels", _docx_package_rels_xml())
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", _docx_document_rels_xml())


def _docx_content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""


def _docx_package_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _docx_document_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""


def _docx_document_xml(paragraphs: list[tuple[str, str]]) -> str:
    body = "\n".join(_docx_paragraph(kind, text) for kind, text in paragraphs)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
{body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1008" w:right="1152" w:bottom="1008" w:left="1152" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""


def _docx_paragraph(kind: str, text: str) -> str:
    run_props = ""
    if kind == "title":
        run_props = "<w:rPr><w:b/><w:sz w:val=\"28\"/></w:rPr>"
    elif kind == "meta":
        run_props = "<w:rPr><w:i/><w:sz w:val=\"20\"/></w:rPr>"
    else:
        run_props = "<w:rPr><w:sz w:val=\"21\"/></w:rPr>"

    safe_text = xml_escape(_valid_xml_text(text))
    return f"""    <w:p>
      <w:r>{run_props}<w:t xml:space="preserve">{safe_text}</w:t></w:r>
    </w:p>"""


def _valid_xml_text(text: str) -> str:
    return "".join(
        char
        for char in text
        if char in "\t\n\r" or ord(char) >= 0x20
    )


def export_response_json(
    output_path: Path,
    response_text: str,
    prompt_name: str | None = None,
    source_pdf: Path | Iterable[Path] | None = None,
) -> Path:
    text = response_text.strip() or "Sem resposta informada."
    source_pdfs = _normalize_source_pdfs(source_pdf)
    payload = {
        "version": 1,
        "source": APP_NAME,
        "type": "resumo_peticao_inicial",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "prompt": prompt_name,
        "arquivos_analisados": [path.name for path in source_pdfs],
        "caminhos_arquivos": [str(path) for path in source_pdfs],
        "resumo": text,
        "resumo_peticao": text,
        "resumo_da_peticao": text,
        "content": text,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _export_with_reportlab(output_path: Path, lines: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    regular_font, bold_font = _reportlab_fonts()
    pages = _paginate(lines)
    doc = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    for page_number, page_lines in enumerate(pages, start=1):
        doc.setFont(bold_font, 13)
        doc.drawString(LEFT, height - 30, APP_NAME)
        doc.setFont(regular_font, 9)
        doc.drawString(LEFT, height - 48, f"Página {page_number} de {len(pages)}")

        y = height - 85
        for line in page_lines:
            if line == DOCUMENT_TITLE:
                doc.setFont(bold_font, 13)
            else:
                doc.setFont(regular_font, BODY_FONT_SIZE)
            doc.drawString(LEFT, y, line)
            y -= LINE_HEIGHT
        doc.showPage()

    doc.save()


def _reportlab_fonts() -> tuple[str, str]:
    if pdfmetrics is None or TTFont is None:
        return "Helvetica", "Helvetica-Bold"

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    regular_path = windows_dir / "Fonts" / "arial.ttf"
    bold_path = windows_dir / "Fonts" / "arialbd.ttf"
    try:
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont("ResumatorArial", str(regular_path)))
            pdfmetrics.registerFont(TTFont("ResumatorArialBold", str(bold_path)))
            return "ResumatorArial", "ResumatorArialBold"
    except Exception:
        pass
    return "Helvetica", "Helvetica-Bold"


def _prepare_lines(response_text: str, prompt_name: str | None, source_pdf: Path | Iterable[Path] | None) -> list[str]:
    header = [
        DOCUMENT_TITLE,
        *_metadata_lines(prompt_name, source_pdf),
    ]
    header.append("")

    text = response_text.strip() or "Sem resposta informada."
    body: list[str] = []
    for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not paragraph.strip():
            body.append("")
            continue
        body.extend(
            textwrap.wrap(
                paragraph,
                width=95,
                break_long_words=True,
                replace_whitespace=False,
            )
        )
    return header + body


def _metadata_lines(prompt_name: str | None, source_pdf: Path | Iterable[Path] | None) -> list[str]:
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    header = [
        f"Aplicativo: {APP_NAME}",
        f"Desenvolvedor: {DEVELOPER}",
        f"Gerado em: {generated_at}",
    ]
    if prompt_name:
        header.append(f"Prompt: {prompt_name}")
    source_pdfs = _normalize_source_pdfs(source_pdf)
    if len(source_pdfs) == 1:
        header.append(f"Arquivo analisado: {source_pdfs[0].name}")
    elif source_pdfs:
        header.append(f"Arquivos analisados: {', '.join(path.name for path in source_pdfs)}")
    return header


def _normalize_source_pdfs(source_pdf: Path | Iterable[Path] | None) -> list[Path]:
    if source_pdf is None:
        return []
    if isinstance(source_pdf, Path):
        return [source_pdf]
    return [Path(path) for path in source_pdf]


def _paginate(lines: list[str]) -> list[list[str]]:
    max_lines = int((TOP - BOTTOM) / LINE_HEIGHT) - 2
    pages: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if len(current) >= max_lines:
            pages.append(current)
            current = []
        current.append(line)

    pages.append(current or [""])
    return pages


def _build_pdf(pages: list[list[str]]) -> bytes:
    page_streams = [_page_content(lines, index + 1, len(pages)) for index, lines in enumerate(pages)]
    page_count = len(page_streams)

    font_regular_id = 3
    font_bold_id = 4
    first_content_id = 5
    first_page_id = first_content_id + page_count
    max_id = first_page_id + page_count - 1

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    }

    kids = []
    for index, stream in enumerate(page_streams):
        content_id = first_content_id + index
        page_id = first_page_id + index
        kids.append(f"{page_id} 0 R")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")

    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {page_count} >>".encode("ascii")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_id + 1)
    for obj_id in range(1, max_id + 1):
        offsets[obj_id] = len(output)
        output.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        output.extend(objects[obj_id])
        output.extend(b"\nendobj\n")

    xref_at = len(output)
    output.extend(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_id + 1):
        output.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)


def _page_content(lines: list[str], page_number: int, total_pages: int) -> bytes:
    commands: list[bytes] = []
    commands.append(_draw_text(LEFT, 762, "F2", 13, APP_NAME))
    commands.append(_draw_text(LEFT, 744, "F1", 9, f"Página {page_number} de {total_pages}"))

    y = TOP - 28
    for line in lines:
        if line == DOCUMENT_TITLE:
            commands.append(_draw_text(LEFT, y, "F2", 13, line))
        else:
            commands.append(_draw_text(LEFT, y, "F1", BODY_FONT_SIZE, line))
        y -= LINE_HEIGHT

    return b"".join(commands)


def _draw_text(x: int, y: int, font: str, size: int, text: str) -> bytes:
    return (
        f"BT /{font} {size} Tf {x} {y} Td ".encode("ascii")
        + _pdf_string(text)
        + b" Tj ET\n"
    )


def _pdf_string(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"(" + raw + b")"
