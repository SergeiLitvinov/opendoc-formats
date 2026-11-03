"""Serialize extracted plain text independently of OCR engines or applications."""

from pathlib import Path

from opendoc_formats.support.io import atomic_write_bytes, atomic_write_text


def write_extracted_text(text: str, output_path: str | Path, *, format_id: str) -> Path:
    out_path = Path(output_path)
    fmt = format_id
    if fmt == "docx":
        import io

        from docx import Document as DocxDocument

        docx = DocxDocument()
        for paragraph in text.split("\n\n"):
            if paragraph.strip():
                docx.add_paragraph(paragraph.strip())
        buffer = io.BytesIO()
        docx.save(buffer)
        atomic_write_bytes(out_path, buffer.getvalue())
    elif fmt == "tex":
        from opendoc_formats.support.latex import escape_latex

        latex = (
            "\\documentclass[12pt,a4paper]{article}\n"
            "\\usepackage[T2A]{fontenc}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage[russian]{babel}\n"
            "\\usepackage{geometry}\n"
            "\\geometry{top=2cm,bottom=2cm,left=2cm,right=2cm}\n\n"
            "\\begin{document}\n\n"
            f"{escape_latex(text)}\n\n"
            "\\end{document}\n"
        )
        atomic_write_text(out_path, latex, encoding="utf-8")
    else:
        atomic_write_text(out_path, text, encoding="utf-8")
    return out_path
