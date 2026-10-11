"""Independent model-to-LaTeX adapter using the established DOCX bridge."""

from pathlib import Path
from tempfile import TemporaryDirectory

from opendoc_model import ConversionReport, DocumentLimits, DocumentModel, IssueSeverity

from opendoc_formats.writers.docx_to_latex import DocxToLatexConverter
from opendoc_formats.writers.docx_writer import write_docx_model


def write_latex_model(
    document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None = None,
) -> ConversionReport:
    output = Path(output_path)
    report = ConversionReport(output)
    with TemporaryDirectory(prefix="opendoc-formats-latex-") as directory:
        intermediate = Path(directory) / "document.docx"
        first = write_docx_model(document, intermediate, limits=limits)
        report.issues.extend(first.issues)
        if not first.success:
            return report
        second = DocxToLatexConverter().convert(intermediate, output)
        report.issues.extend(second.issues)
        report.metrics.update(second.metrics)
    report.add(
        IssueSeverity.LOSS, "latex-layout", "LaTeX uses the DOCX bridge; exact layout and complex objects are not guaranteed"
    )
    return report
