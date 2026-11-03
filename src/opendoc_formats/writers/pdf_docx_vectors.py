"""Keep supported PDF path objects as separate, positioned Word SVG pictures."""

from __future__ import annotations

from dataclasses import replace
from xml.etree import ElementTree as ET

from opendoc_model import Box, DocumentModel, Image, Resource, ResourceKind

from opendoc_formats.support.cancellation import checkpoint


def convert_vector(document: DocumentModel, image: Image, location: str) -> None:
    checkpoint()
    resource = document.resources.get(image.resource_id)
    if resource is None or resource.media_type != 'application/pdf+vector':
        return
    if resource.properties.get('neutral_page_group_only'):
        resource = replace(resource, properties={**resource.properties, 'graphics_state_unsupported': False})
    if image.properties.get('pdf_docx_graphics_measured'):
        resource = replace(resource, properties={**resource.properties, 'graphics_state_unsupported': False, 'clip_rects': []})
    from opendoc_formats.writers.pdf_vectors import PdfVector, _validate, draw_vectors

    _validate(image, resource)
    import pymupdf as fitz

    assert image.box is not None
    original = image.box
    if min(original.width, original.height) <= 0:
        raise ValueError(f'{location}: isolated zero-area PDF strokes require a verified native Word line profile')
    padding = max(float(resource.properties.get('width', 1)) / 2 + .1, .5)
    width, height = original.width + 2 * padding, original.height + 2 * padding
    with fitz.open() as native:
        page = native.new_page(width=width, height=height)
        placed = replace(image, box=Box(padding, padding, original.width, original.height))

        def cancelled() -> bool:
            # Raise the format cancellation before the legacy renderer maps True to ValueError.
            checkpoint()
            return False

        draw_vectors(page, [PdfVector(placed, resource, location)], cancelled)
        checkpoint()
        svg = page.get_svg_image(text_as_path=False).encode('utf-8')
    from opendoc_formats.writers.pdf_docx_graphics import clip_svg, word_svg_bytes

    root = ET.fromstring(svg)
    clips = image.properties.get('pdf_docx_clip_paths')
    if clips:
        clip_svg(root, clips, Box(original.x-padding, original.y-padding, width, height),
                 max_commands=image.properties.get('pdf_docx_clip_limit', 50_000))
    svg = word_svg_bytes(root)
    identifier = resource.id + '-word-svg'
    while identifier in document.resources:
        checkpoint()
        identifier += '-derived'
    document.resources[identifier] = Resource(identifier, ResourceKind.VECTOR_IMAGE, media_type='image/svg+xml',
                                              data=svg, properties={'pdf_source_resource': resource.id},
                                              provenance=resource.provenance)
    image.resource_id = identifier
    image.box = Box(original.x - padding, original.y - padding, width, height)
