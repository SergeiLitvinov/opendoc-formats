"""Preserve physical absence of Word docDefaults without inventing host defaults."""

from __future__ import annotations

from typing import Any

from opendoc_model import DocumentModel
from opendoc_model.diagnostics import ConversionReport, IssueSeverity

from opendoc_formats.support.cancellation import checkpoint

KEY = 'opendoc_formats.docx_defaults'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def source_defaults(document: Any) -> dict[str, Any]:
    """Call before document.styles can create a template part on lazy access."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    checkpoint()
    try:
        part = document.part.part_related_by(RT.STYLES)
    except KeyError:
        part = None
    return {'format': KEY, 'version': 1, 'styles_present': part is not None,
            'doc_defaults_present': part is not None and part.element.find(W+'docDefaults') is not None}


def restore_absent_defaults(target: Any, document: DocumentModel, report: ConversionReport) -> None:
    checkpoint()
    state = document.metadata.get(KEY)
    if state is None:
        return
    if (not isinstance(state, dict) or state.get('format') != KEY or type(state.get('version')) is not int
            or state['version'] != 1 or type(state.get('styles_present')) is not bool
            or type(state.get('doc_defaults_present')) is not bool
            or (not state['styles_present'] and state['doc_defaults_present'])):
        report.add(IssueSeverity.ERROR, 'docx.defaults', 'Invalid or unsupported source defaults profile', f'metadata[{KEY}]')
        return
    if state['doc_defaults_present']:
        return
    for node in list(target.styles.element.findall(W+'docDefaults')):
        checkpoint()
        target.styles.element.remove(node)


def created_defaults(document: DocumentModel) -> bool:
    """A new declaration must also survive replay of an original styles part."""
    state = document.metadata.get(KEY)
    if not isinstance(state, dict) or state.get('doc_defaults_present') is not False:
        return False
    for identifier, style in document.styles.items():
        checkpoint()
        if identifier == '__doc_defaults__' or style.properties.style_type == 'document-default':
            return True
    return False
