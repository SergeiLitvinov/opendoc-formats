"""Keep supported PDF path objects as separate, positioned Word SVG pictures."""

from __future__ import annotations

from dataclasses import replace

from opendoc_model import Box, DocumentModel, Image, Resource, ResourceKind


def convert_vector(document: DocumentModel, image: Image, location: str) -> None:
    resource = document.resources.get(image.resource_id)
    if resource is None or resource.media_type != 'application/pdf+vector':
        return
    if resource.properties.get('neutral_page_group_only'):
        resource = replace(resource, properties={**resource.properties, 'graphics_state_unsupported': False})
    from opendoc_formats.writers.pdf_vectors import PdfVector, _validate, draw_vectors

    _validate(image, resource)
    import fitz

    assert image.box is not None
    original = image.box
    if min(original.width, original.height) <= 0:
        raise ValueError(f'{location}: isolated zero-area PDF strokes require a verified native Word line profile')
    padding = max(float(resource.properties.get('width', 1)) / 2 + .1, .5)
    width, height = original.width + 2 * padding, original.height + 2 * padding
    with fitz.open() as native:
        page = native.new_page(width=width, height=height)
        placed = replace(image, box=Box(padding, padding, original.width, original.height))
        draw_vectors(page, [PdfVector(placed, resource, location)], lambda: False)
        svg = page.get_svg_image(text_as_path=False).encode('utf-8')
    identifier = resource.id + '-word-svg'
    while identifier in document.resources:
        identifier += '-derived'
    document.resources[identifier] = Resource(identifier, ResourceKind.VECTOR_IMAGE, media_type='image/svg+xml',
                                              data=svg, properties={'pdf_source_resource': resource.id},
                                              provenance=resource.provenance)
    image.resource_id = identifier
    image.box = Box(original.x - padding, original.y - padding, width, height)
