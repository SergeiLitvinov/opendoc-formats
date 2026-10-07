"""Plain-text input without application types or optional dependencies."""

from pathlib import Path

from opendoc_model import DocumentModel, Paragraph, Section, TextRun


def read_txt_model(path: str | Path) -> DocumentModel:
    source = Path(path)
    try:
        text, encoding = source.read_text(encoding="utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, encoding = source.read_text(encoding="cp1251"), "cp1251"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return DocumentModel(
        source_format="txt",
        sections=[Section(blocks=[Paragraph([TextRun(line)]) for line in normalized.split("\n")])],
        metadata={"engine": encoding, "source_name": source.name, "txt": {"line_separator": "\n"}},
    )
