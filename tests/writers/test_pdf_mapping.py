"""Actual raster occurrences, source immutability and outer publication rollback."""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import Event

import pymupdf
import pytest
from opendoc_model import (
    PreservationState,
    Resource,
    ResourceKind,
    VisualSurrogate,
    document_from_json,
    document_to_json,
    object_mapping_from_dict,
    object_mapping_to_dict,
    validate_object_mapping,
)

from opendoc_formats import ExportOptions, read_document, write_document
from opendoc_formats.support.object_mapping import get_object_mapping


def _document():
    source = Path(__file__).parents[1] / 'corpus/native/vector-export.pdf'
    document = read_document(source).document
    image = document.sections[0].blocks[0].content[0]
    document.resources[image.resource_id].properties['items'] = [['unknown']]
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pixmap.clear_with(120)
    document.resources['visual'] = Resource('visual', ResourceKind.RASTER_IMAGE, 'image/png', data=pixmap.tobytes('png'))
    image.visual_surrogate = VisualSurrogate('visual', 'unsupported vector', 'image/png')
    second = deepcopy(image)
    second.box = replace(second.box, x=60, y=60)
    document.sections[0].blocks[0].content.append(second)
    return document


def _check(mapping, output, count):
    assert mapping.publication == 'published'
    assert mapping.assessment_complete
    assert len(mapping.sources) == len(mapping.entries) == len(mapping.targets) == count
    assert mapping.result_id == 'sha256:' + hashlib.sha256(output.read_bytes()).hexdigest()
    assert all(entry.state is PreservationState.VISUAL and entry.issue.reason for entry in mapping.entries)
    assert all(entry.replacement.resource_id == 'visual' for entry in mapping.entries)
    with pymupdf.open(output) as pdf:
        locations = []
        for target in mapping.targets:
            location = json.loads(target.native_locator.value)
            actual = pdf[location['page']].get_image_info(hashes=True, xrefs=True)[location['image']]
            assert actual['xref'] == location['xref']
            assert actual['digest'].hex() == location['digest']
            assert list(actual['bbox']) == location['bbox']
            locations.append((location['page'], location['image']))
        assert len(set(locations)) == count


def test_occurrences_reorder_delete_and_codec_do_not_use_resource_as_identity(tmp_path):
    document = _document()
    for cycle, count in enumerate((2, 2, 1)):
        document = document_from_json(document_to_json(document))
        original = document_to_json(document)
        output = tmp_path / f'cycle{cycle}.pdf'
        report = write_document(document, output)
        assert report.success, report.to_dict()
        mapping = get_object_mapping(report)
        validate_object_mapping(mapping, source=document)
        for _ in range(2):
            mapping = object_mapping_from_dict(json.loads(json.dumps(object_mapping_to_dict(mapping))))
        _check(mapping, output, count)
        assert document_to_json(document) == original
        assert len(read_document(output).document.sections[0].blocks) > 0
        images = document.sections[0].blocks[0].content
        if cycle == 0:
            images.reverse()
        elif cycle == 1:
            images.pop()
    moved = tmp_path / 'relocated.pdf'
    output.rename(moved)
    _check(mapping, moved, 1)


@pytest.mark.parametrize('case', ['quality', 'cancel', 'changed', 'deleted', 'callback-error', 'publication'])
def test_outer_refusal_clears_actual_targets_and_keeps_previous_file(tmp_path, monkeypatch, case):
    output = tmp_path / 'output.pdf'
    output.write_bytes(b'previous')
    stop = Event()

    def gate(report, staged):
        mapping = get_object_mapping(report)
        assert mapping.publication == 'staged' and mapping.targets
        if case == 'cancel':
            stop.set()
        if case == 'callback-error':
            raise ValueError('Own gate failure')
        if case == 'changed':
            staged.write_bytes(staged.read_bytes() + b'\nOwn changed bytes\n')
        if case == 'deleted':
            staged.unlink()
        return report.lossless if case == 'quality' else True

    if case == 'publication':
        import opendoc_formats.export as module
        native = module.os.replace

        def fail(source, target):
            if Path(target) == output:
                raise OSError('Own publication failure')
            return native(source, target)

        monkeypatch.setattr(module.os, 'replace', fail)
    report = write_document(_document(), output, options=ExportOptions(cancelled=stop.is_set, quality_gate=gate))
    assert not report.success
    mapping = get_object_mapping(report)
    assert mapping.publication == ('invalidated' if case in ('changed', 'deleted') else 'rejected')
    assert not mapping.assessment_complete and not mapping.targets
    assert all(entry.target_ids is None for entry in mapping.entries)
    assert mapping.publication_issue.reason
    assert output.read_bytes() == b'previous'


@pytest.mark.parametrize('phase', ['entry', 'preparation'])
def test_early_cancellation_does_not_invent_a_mapping_or_replace_destination(tmp_path, monkeypatch, phase):
    import opendoc_formats.writers.pdf_writer as writer

    document = _document()
    before = document_to_json(document)
    output = tmp_path/'keep.pdf'
    output.write_bytes(b'previous')
    stop = Event()
    if phase == 'entry':
        stop.set()
    else:
        original = writer.document_font_resolver

        @contextmanager
        def interrupted(*args, **kwargs):
            stop.set()
            with original(*args, **kwargs) as resolver:
                yield resolver

        monkeypatch.setattr(writer, 'document_font_resolver', interrupted)
    report = write_document(document, output, options=ExportOptions(cancelled=stop.is_set))
    assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
    assert get_object_mapping(report) is None
    assert output.read_bytes() == b'previous' and document_to_json(document) == before
    assert [path.name for path in tmp_path.iterdir()] == ['keep.pdf']


def test_unsupported_without_surrogate_has_typed_rejected_attempt(tmp_path):
    document = _document()
    for image in document.sections[0].blocks[0].content:
        image.visual_surrogate = None
    output = tmp_path / 'output.pdf'
    output.write_bytes(b'previous')
    report = write_document(document, output)
    mapping = get_object_mapping(report)
    assert not report.success and mapping.publication == 'rejected'
    assert all(entry.state is PreservationState.REJECTED for entry in mapping.entries)
    assert not mapping.targets and output.read_bytes() == b'previous'


def test_removed_native_vector_does_not_shift_fallback_occurrence_binding(tmp_path):
    document = _document()
    native = deepcopy(document.sections[0].blocks[0].content[0])
    native.resource_id = 'native'
    native.box = replace(native.box, x=1, y=1, width=1, height=1)
    native.visual_surrogate = None
    document.resources['native'] = Resource(
        'native', ResourceKind.VECTOR_IMAGE, 'application/pdf+vector', data=b'{}', properties={
        'items': [['l', [1, 1], [2, 2]]], 'bbox': [1, 1, 2, 2], 'width': 1, 'dashes': '[] 0',
        'line_cap': 0, 'line_join': 0,
    })
    document.sections[0].blocks[0].content.insert(0, native)
    output = tmp_path / 'mixed.pdf'
    report = write_document(document, output)
    assert report.success, report.to_dict()
    _check(get_object_mapping(report), output, 2)


def test_input_properties_cannot_forge_another_fallback_occurrence(tmp_path):
    document = _document()
    raster = deepcopy(document.sections[0].blocks[0].content[0])
    raster.resource_id = 'visual'
    raster.visual_surrogate = None
    raster.box = replace(raster.box, x=20, y=80)
    raster.properties['_opendoc_formats_mapping'] = 0
    document.sections[0].blocks[0].content.insert(0, raster)
    output = tmp_path / 'own.pdf'
    report = write_document(document, output)
    assert report.success, report.to_dict()
    _check(get_object_mapping(report), output, 2)
