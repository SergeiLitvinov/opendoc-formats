"""Native text-to-TeX export, with the established bridge for other objects."""

from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from opendoc_model import ArtifactLimitError, ConversionReport, DocumentLimits, DocumentModel, IssueSeverity

from opendoc_formats.support.cancellation import cancellable_items, cancellation_scope, checkpoint
from opendoc_formats.support.io import atomic_copy, atomic_write_bytes


def write_latex_model(
    document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ConversionReport:
    """Write native TeX or the established bridge, cancelling before publication."""
    with cancellation_scope(cancelled, 'TeX export', check_on_exit=False):
        return _write_latex_model(document, output_path, limits=limits, cancelled=cancelled)


def _write_latex_model(
    document: DocumentModel, output_path: str | Path, *, limits: DocumentLimits | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> ConversionReport:
    output = Path(output_path)
    report = ConversionReport(output)
    for error in document.validate(limits=limits):
        report.add(IssueSeverity.ERROR, 'model', error)
    if not report.success:
        return report
    from opendoc_model import Formula, TextRun, walk_model

    from opendoc_formats.writers.latex_text import _TextScriptProfileError, native_text

    has_formulas = any(isinstance(ref.node, Formula) for ref in walk_model(document, limits=limits))
    has_scripts = any(isinstance(ref.node, TextRun) and (ref.node.style.superscript or ref.node.style.subscript)
                      for ref in cancellable_items(walk_model(document, limits=limits)))

    try:
        source = native_text(document, limits=limits)
    except ArtifactLimitError:
        raise
    except _TextScriptProfileError as error:
        report.add(IssueSeverity.ERROR, 'latex.text-script-profile', str(error))
        return report
    except ValueError as error:
        report.add(IssueSeverity.ERROR, 'latex.formula-profile' if has_formulas else
                   'latex.text-script-profile' if has_scripts else 'latex.list-profile', str(error))
        return report
    if source is not None:
        atomic_write_bytes(output, source.encode('utf-8'), max_bytes=None, before_replace=checkpoint)
        report.metrics.update(latex_route='native-text-v1', assessment_complete=False)
        report.add(IssueSeverity.LOSS, 'latex-layout', 'Native TeX preserves the finite text profile, not measured page layout')
        return report
    from opendoc_model import LIST_PROPERTY, Paragraph, get_integration, get_list_item, walk_model

    from opendoc_formats.support.backends import missing_backends

    integration = get_integration(document, limits=limits)
    if has_scripts or integration and any((r.issue.reason or '').startswith('text-script-') for r in integration.preservation):
        report.add(IssueSeverity.ERROR, 'latex.text-script-profile',
                   'Text scripts outside the native profile cannot use the DOCX bridge without losing their structure')
        return report
    if (has_formulas or integration and (integration.formula_trees
            or any((r.issue.reason or '').startswith('math-') for r in integration.preservation))):
        report.add(IssueSeverity.ERROR, 'latex.formula-profile',
                   'Formula structure is outside the native profile; the DOCX bridge is not a structural substitute')
        return report
    if (any(isinstance(ref.node, Paragraph) and (get_list_item(ref.node, limits=limits) is not None
            or LIST_PROPERTY in ref.node.properties or 'latex_list_id' in ref.node.properties)
            for ref in walk_model(document, limits=limits))
            or integration and any((r.issue.reason or '').startswith('list-') for r in integration.preservation)):
        report.add(IssueSeverity.ERROR, 'latex.list-profile',
                   'List structure is outside the native profile; the DOCX bridge is not a structural substitute')
        return report

    if missing_backends(('docx',)):
        report.add(IssueSeverity.ERROR, 'latex.docx-bridge',
                   'Objects outside the native text profile require opendoc-formats[docx] for the existing DOCX bridge')
        return report
    from opendoc_formats.writers.docx_to_latex import DocxToLatexConverter
    from opendoc_formats.writers.docx_writer import write_docx_model

    report.metrics['latex_route'] = 'docx-bridge'
    with TemporaryDirectory(prefix="opendoc-formats-latex-") as directory:
        intermediate = Path(directory) / "document.docx"
        first = write_docx_model(document, intermediate, limits=limits, cancelled=cancelled)
        checkpoint()
        report.issues.extend(first.issues)
        if not first.success:
            return report
        staged = Path(directory) / 'output.tex'
        second = DocxToLatexConverter().convert(intermediate, staged)
        checkpoint()
        report.issues.extend(second.issues)
        report.metrics.update(second.metrics)
        if second.success:
            atomic_copy(staged, output, max_bytes=None, before_replace=checkpoint)
    report.add(
        IssueSeverity.LOSS, "latex-layout", "LaTeX uses the DOCX bridge; exact layout and complex objects are not guaranteed"
    )
    return report
