"""Native text-to-TeX export, with the established bridge for other objects."""

from pathlib import Path
from tempfile import TemporaryDirectory

from opendoc_model import ConversionReport, DocumentLimits, DocumentModel, IssueSeverity


def write_latex_model(
    document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None = None,
) -> ConversionReport:
    output = Path(output_path)
    report = ConversionReport(output)
    for error in document.validate(limits=limits):
        report.add(IssueSeverity.ERROR, 'model', error)
    if not report.success:
        return report
    from opendoc_formats.writers.latex_text import native_text

    source = native_text(document, limits=limits)
    if source is not None:
        output.write_bytes(source.encode('utf-8'))
        report.metrics.update(latex_route='native-text-v1', assessment_complete=False)
        report.add(IssueSeverity.LOSS, 'latex-layout', 'Native TeX preserves the finite text profile, not measured page layout')
        return report
    from opendoc_formats.support.backends import missing_backends

    if missing_backends(('docx',)):
        report.add(IssueSeverity.ERROR, 'latex.docx-bridge',
                   'Objects outside the native text profile require opendoc-formats[docx] for the existing DOCX bridge')
        return report
    from opendoc_formats.writers.docx_to_latex import DocxToLatexConverter
    from opendoc_formats.writers.docx_writer import write_docx_model

    report.metrics['latex_route'] = 'docx-bridge'
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
