"""Generated replacements refer to measured target resources, never source SVG IDs."""

import hashlib
import json

import pymupdf
import pytest
from opendoc_model import (
    Box,
    DocumentModel,
    Image,
    Paragraph,
    PreservationState,
    Provenance,
    Resource,
    ResourceKind,
    Section,
    TextRun,
    document_from_json,
    document_to_json,
    validate_object_mapping,
)

from opendoc_formats import ExportOptions, get_object_mapping, read_document, read_pdf_origin_mapping, write_document
from opendoc_formats.writers.html_resources import document_images
from opendoc_formats.writers.pdf_resources import PdfResourceStage
from opendoc_formats.writers.stages import StageContext

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="red"/></svg>'


def _document(positioned=False, shared=False):
    first = Image('svg', box=Box(10, 10, 40, 20) if positioned else None)
    second = first if shared else Image('svg', box=Box(80, 40, 40, 20) if positioned else None)
    return DocumentModel(
        resources={'svg': Resource('svg', ResourceKind.VECTOR_IMAGE, 'image/svg+xml', data=SVG,
                                   provenance=Provenance('svg', source_path='own.svg', object_id='own-rect'))},
        sections=[Section(blocks=[Paragraph([first]), Paragraph([second])])],
    )


@pytest.mark.parametrize('positioned,shared', [(False, False), (True, False), (False, True)])
def test_generated_svg_png_mapping_and_two_full_cycles(tmp_path, positioned, shared):
    document = _document(positioned, shared)
    before = document_to_json(document)
    output = tmp_path / 'initial.pdf'
    report = write_document(document, output)
    assert report.success, report.to_dict()
    mapping = get_object_mapping(report)
    assert mapping.assessment_complete and len(mapping.sources) == len(mapping.entries) == len(mapping.targets) == 2
    snapshot = read_document(output).document
    validate_object_mapping(mapping, source=document, target=snapshot)
    assert mapping.result_id == 'sha256:' + hashlib.sha256(output.read_bytes()).hexdigest()
    with pymupdf.open(output) as pdf:
        for entry in mapping.entries:
            assert entry.state is PreservationState.VISUAL and entry.issue.code == 'pdf.svg-rasterized'
            assert entry.replacement.scope == 'target' and entry.replacement.resource_id != 'svg'
            assert snapshot.resources[entry.replacement.resource_id].kind is ResourceKind.RASTER_IMAGE
        for occurrence in mapping.targets:
            locator = json.loads(occurrence.native_locator.value)
            native = pdf[locator['page']].get_image_info(hashes=True, xrefs=True)[locator['image']]
            assert native['xref'] == locator['xref'] and native['digest'].hex() == locator['digest']
            assert list(native['bbox']) == locator['bbox']
    assert document_to_json(document) == before
    origins = {source.id: source.provenance for source in read_pdf_origin_mapping(output).sources}
    assert len(origins) == 2 and all(item.source_path == 'own.svg' for item in origins.values())
    for cycle in range(2):
        document = document_from_json(document_to_json(read_document(output).document))
        document.sections[0].blocks.reverse()
        output = tmp_path / f'cycle-{cycle}.pdf'
        report = write_document(document, output)
        assert report.success, report.to_dict()
        restored = read_pdf_origin_mapping(output)
        assert restored.assessment_complete and {source.id: source.provenance for source in restored.sources} == origins
        validate_object_mapping(restored, target=read_document(output).document)
    document = read_document(output).document
    document.sections[0].blocks.pop()
    live = {image.resource_id for image, _ in document_images(document)}
    document.resources = {key: resource for key, resource in document.resources.items()
                          if key in live or resource.media_type == 'application/pdf'}
    final = tmp_path / 'deleted.pdf'
    assert write_document(document, final).success
    restored = read_pdf_origin_mapping(final)
    assert len(restored.sources) == len(restored.targets) == 1
    assert {source.id for source in restored.sources} < set(origins)


def test_generated_target_claims_are_cleared_on_quality_rejection(tmp_path):
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous')
    measured = []

    def reject(report, staged):
        mapping = get_object_mapping(report)
        assert mapping.publication == 'staged' and mapping.assessment_complete
        assert all(entry.replacement.scope == 'target' for entry in mapping.entries)
        validate_object_mapping(mapping, source=document, target=read_document(staged).document)
        measured.append(mapping)
        return False

    document = _document()
    report = write_document(document, output, options=ExportOptions(quality_gate=reject))
    assert measured and not report.success and output.read_bytes() == b'previous'
    mapping = get_object_mapping(report)
    assert mapping.publication == 'rejected' and not mapping.targets and not mapping.assessment_complete
    assert all(entry.target_ids is None and entry.replacement is None for entry in mapping.entries)


@pytest.mark.parametrize('transparent,mixed', [(False, False), (True, False), (True, True)])
def test_intrinsic_svg_flow_matches_prepared_png_pixels_and_size(tmp_path, transparent, mixed):
    document = _document()
    if transparent:
        document.resources['svg'].data = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
            b'<circle cx="20" cy="10" r="8" fill="blue" opacity="0.4"/></svg>'
        )
    if mixed:
        for block in document.sections[0].blocks:
            block.content = [TextRun('Own prefix '), *block.content, TextRun(' own suffix')]
    baseline = PdfResourceStage().execute(document, StageContext(tmp_path / 'prepared.pdf')).value
    reference = tmp_path / 'prepared.pdf'
    actual = tmp_path / 'mapped.pdf'
    assert write_document(baseline, reference).success
    assert write_document(document, actual).success
    with pymupdf.open(reference) as before, pymupdf.open(actual) as after:
        assert len(before) == len(after) == 1
        assert before[0].get_pixmap(alpha=False).samples == after[0].get_pixmap(alpha=False).samples
        expected = [item['bbox'] for item in before[0].get_image_info()]
        observed = [item['bbox'] for item in after[0].get_image_info()]
        assert observed == expected


def test_repeated_header_is_one_source_with_measured_targets_on_each_page(tmp_path):
    document = _document()
    document.sections[0].headers = [Image('svg')]
    document.sections[0].blocks += [Paragraph([TextRun('Own repeated text ' * 10)]) for _ in range(40)]
    output = tmp_path / 'pages.pdf'
    report = write_document(document, output)
    assert report.success, report.to_dict()
    mapping = get_object_mapping(report)
    assert mapping.assessment_complete
    header = next(entry for entry in mapping.entries if '.headers[' in entry.issue.location)
    with pymupdf.open(output) as pdf:
        assert len(pdf) > 1 and len(header.target_ids) == len(pdf)
    validate_object_mapping(mapping, source=document, target=read_document(output).document)


def test_failed_svg_rasterization_is_rejected_and_atomic(tmp_path):
    document = _document()
    document.resources['svg'].data = b'broken SVG'
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous')
    report = write_document(document, output)
    assert not report.success and output.read_bytes() == b'previous'
    mapping = get_object_mapping(report)
    assert mapping.publication == 'rejected' and len(mapping.sources) == 2
    assert not mapping.targets and all(entry.state is PreservationState.REJECTED for entry in mapping.entries)


def test_unconfirmed_temporary_pixels_never_reach_published_output(tmp_path, monkeypatch):
    from opendoc_formats.support.object_mapping import PdfFallbackMapping

    original = PdfFallbackMapping.prepare_story
    resolver = PdfFallbackMapping.resolve_story
    native_documents = []

    def corrupt_digest(self, document):
        original(self, document)
        self.story_markers = {index: (b'unknown-digest!!!', marker, source)
                              for index, (_, marker, source) in self.story_markers.items()}

    monkeypatch.setattr(PdfFallbackMapping, 'prepare_story', corrupt_digest)
    def record_document(self, pdf, offset):
        native_documents.append(pdf)
        return resolver(self, pdf, offset)

    monkeypatch.setattr(PdfFallbackMapping, 'resolve_story', record_document)
    output = tmp_path / 'previous.pdf'
    output.write_bytes(b'previous')
    report = write_document(_document(), output)
    assert not report.success and output.read_bytes() == b'previous'
    assert any(issue.feature == 'pdf.svg-target-unconfirmed' and issue.location for issue in report.issues)
    mapping = get_object_mapping(report)
    assert mapping.publication == 'rejected' and not mapping.targets
    assert native_documents and all(pdf.is_closed for pdf in native_documents)
