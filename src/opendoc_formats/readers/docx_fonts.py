"""Decode document-owned Word font programs into bounded Model resources."""

from __future__ import annotations

from uuid import UUID

from opendoc_model import ArtifactLimitError, DocumentLimits, DocumentModel, Provenance, Resource, ResourceKind

from opendoc_formats.support.cancellation import cancellable_items, checkpoint

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def read_embedded_fonts(document: object, *, limits: DocumentLimits | None = None) -> dict[str, Resource]:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from lxml import etree

    from opendoc_formats.fonts.docx_embedding import _obfuscate

    try:
        table = document.part.part_related_by(RT.FONT_TABLE)
    except KeyError:
        return {}
    root = etree.fromstring(table.blob, etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True))
    result = {}
    total = 0
    budget = limits or DocumentLimits()
    for font in root.findall(W + 'font'):
        checkpoint()
        for tag in ('embedRegular', 'embedBold', 'embedItalic', 'embedBoldItalic'):
            checkpoint()
            for node in font.findall(W + tag):
                checkpoint()
                relationship = table.rels.get(node.get(R + 'id'))
                if relationship is None or relationship.is_external or relationship.reltype != RT.FONT:
                    raise ValueError('Embedded Word font has an invalid or external relationship')
                key = UUID(node.get(W + 'fontKey', '').strip('{}'))
                payload = _obfuscate(relationship.target_part.blob, key)
                total += len(payload)
                identifier = f'docx-font-{len(result)}'
                if total > budget.max_embedded_bytes:
                    raise ArtifactLimitError('Word font programs exceed embedded-byte budget',
                                             path=f'$.resources[{identifier!r}]', quota='embedded bytes',
                                             maximum=budget.max_embedded_bytes)
                media = 'font/otf' if payload[:4] == b'OTTO' else 'font/ttf'
                result[identifier] = Resource(identifier, ResourceKind.FONT, media_type=media, data=payload,
                                              filename=f'{identifier}.ttf', properties={'docx_font_family': font.get(W + 'name'),
                                                                                       'docx_font_variant': tag},
                                              provenance=Provenance(source_format='docx',
                                                                    package_part=str(relationship.target_part.partname)))
    return result


def attach_font_references(model: DocumentModel, *, limits: DocumentLimits | None = None) -> None:
    """Bind parsed Word font-table slots, independently of the binary family name."""
    from opendoc_model import FontReference, TextRun, get_font_reference, set_font_reference, walk_model

    slots = {}
    for resource in model.resources.values():
        checkpoint()
        if resource.kind is ResourceKind.FONT:
            key = (resource.properties.get('docx_font_family'), resource.properties.get('docx_font_variant'))
            slots.setdefault(key, []).append(resource.id)
    styles = list(model.styles.values()) + [location.node.style
                                           for location in cancellable_items(walk_model(model, limits=limits))
                                           if isinstance(location.node, TextRun)]
    for style in styles:
        checkpoint()
        variant = ('embedBoldItalic' if style.bold and style.italic else 'embedBold' if style.bold else
                   'embedItalic' if style.italic else 'embedRegular')
        candidates = slots.get((style.font_family, variant), [])
        if len(candidates) == 1 and get_font_reference(style, limits=limits) is None:
            set_font_reference(style, FontReference(candidates[0]), limits=limits)
