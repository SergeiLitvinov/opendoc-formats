"""Decode document-owned Word font programs into bounded Model resources."""

from __future__ import annotations

from uuid import UUID

from opendoc_model import ArtifactLimitError, DocumentLimits, Provenance, Resource, ResourceKind

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
        for tag in ('embedRegular', 'embedBold', 'embedItalic', 'embedBoldItalic'):
            for node in font.findall(W + tag):
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
