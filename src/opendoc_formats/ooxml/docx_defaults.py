"""Preserve absent Word defaults/settings without inventing template declarations."""

from __future__ import annotations

from typing import Any

from opendoc_model import DocumentModel
from opendoc_model.diagnostics import ConversionReport, IssueSeverity

from opendoc_formats.support.cancellation import checkpoint

KEY = 'opendoc_formats.docx_defaults'
SETTINGS_KEY = 'opendoc_formats.docx_settings'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def source_settings(document: Any) -> dict[str, Any]:
    """Inspect the physical relationship before lazy settings access creates a part."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    checkpoint()
    try:
        document.part.part_related_by(RT.SETTINGS)
    except KeyError:
        present = False
    else:
        present = True
    return {'format': SETTINGS_KEY, 'version': 1, 'settings_present': present}


def restore_absent_settings(target: Any, document: DocumentModel, report: ConversionReport,
                            *, limits: Any = None) -> None:
    """Restore source settings first; explicit Model edits are applied afterwards."""
    checkpoint()
    state = document.metadata.get(SETTINGS_KEY)
    if state is None:
        return
    if (not isinstance(state, dict) or state.get('format') != SETTINGS_KEY or type(state.get('version')) is not int
            or state['version'] != 1 or type(state.get('settings_present')) is not bool):
        report.add(IssueSeverity.ERROR, 'docx.settings', 'Invalid or unsupported source settings profile',
                   f'metadata[{SETTINGS_KEY}]')
        return
    from opendoc_formats.ooxml.package import RELATIONSHIP_TYPE

    source = document.package.related_part(document.package.root, RELATIONSHIP_TYPE['settings']) if document.package else None
    if (source is not None) != state['settings_present']:
        report.add(IssueSeverity.ERROR, 'docx.settings', 'Source settings disagree with the source presence profile',
                   f'metadata[{SETTINGS_KEY}]')
        return
    restored = None
    if source is not None:
        from docx.oxml import parse_xml
        from opendoc_model import ArtifactLimitError, DocumentLimits

        from opendoc_formats.anatomy import AnatomyLimits, _Budget, _xml_nodes

        budget = limits or DocumentLimits()
        maximum = min(AnatomyLimits().max_part_bytes, budget.max_bytes)
        if not isinstance(source.data, bytes):
            raise ValueError('Source settings require inline XML bytes')
        if len(source.data) > maximum:
            raise ArtifactLimitError('Source settings exceed XML byte budget', path=source.name,
                                     quota='bytes', maximum=maximum)
        xml_limits = AnatomyLimits(max_part_bytes=maximum, max_xml_nodes=budget.max_nodes,
                                   max_xml_depth=budget.max_depth, max_xml_characters=budget.max_bytes)
        _xml_nodes(source.data, source.name, _Budget(xml_limits), count_markup=True)
        restored = parse_xml(source.data)
        if restored.tag != W+'settings':
            raise ValueError('Source settings part has an unexpected root')
        # Keep namespace declarations used by mc:Ignorable and other QName values.
        part = target.part._settings_part
        part._element = restored
        part._settings = restored
        return
    root = target.settings.element
    root.attrib.clear()
    for node in list(root):
        checkpoint()
        root.remove(node)


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
