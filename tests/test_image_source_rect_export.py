"""Old Model keeps a future viewport carrier; exporters must not silently drop it."""

from copy import deepcopy

import opendoc_model as od
import pytest

from opendoc_formats import ExporterRegistry, ExporterSpec, read_document, write_document
from tests.writers.test_pdf_docx_rasters import own_pixels

KEY = 'opendoc.image-source-rect'
RECT = {'format': KEY, 'version': 1, 'left': -0.13333, 'top': 0.26667, 'right': 0.86667, 'bottom': 0.86667}


def own_model(raw=None):
    image = od.Image('i', box=od.Box(40, 40, 180, 240), properties={KEY: deepcopy(RECT if raw is None else raw)})
    return od.DocumentModel(sections=[od.Section(blocks=[image])], resources={
        'i': od.Resource('i', od.ResourceKind.RASTER_IMAGE, 'image/png', data=own_pixels()),
    })


@pytest.mark.parametrize('extension', ['html', 'docx', 'pptx', 'pdf', 'epub', 'tex', 'txt'])
def test_unsupported_viewport_refuses_atomically_before_backend(tmp_path, extension):
    model = own_model()
    before = od.document_to_json(model)
    output = tmp_path/f'kept.{extension}'
    output.write_bytes(b'previous')
    report = write_document(model, output)
    assert not report.success, report.issues
    assert any(issue.feature == 'export.image-source-rect' and 'sections[0]' in issue.location for issue in report.issues)
    assert output.read_bytes() == b'previous' and od.document_to_json(model) == before


def test_future_carrier_roundtrips_public_json_twice(tmp_path):
    model = own_model()
    for cycle in range(2):
        output = tmp_path/f'model-{cycle}.json'
        report = write_document(model, output)
        assert report.success, report.issues
        imported = read_document(output)
        assert imported.success, imported.issues
        model = imported.document
        assert model.sections[0].blocks[0].properties[KEY] == RECT


@pytest.mark.parametrize('raw', [{'format': 'future', 'version': 99}, 'opaque', False])
def test_uninterpreted_reserved_carrier_is_not_guessed(tmp_path, raw):
    model = own_model(raw)
    report = write_document(model, tmp_path/'refused.html')
    assert not report.success and any(issue.feature == 'export.image-source-rect' for issue in report.issues)


def test_custom_writer_explicitly_declares_viewport_support(tmp_path):
    calls = []
    def writer(document, path):
        calls.append(document.sections[0].blocks[0].properties[KEY])
        path.write_bytes(b'own handled output')
        return od.ConversionReport(path)
    model = own_model()
    registry = ExporterRegistry()
    registry.register(ExporterSpec('custom', ('.custom',), writer))
    output = tmp_path/'result.custom'
    assert not registry.write(model, output).success
    assert not calls and not output.exists()
    capable = ExporterRegistry()
    capable.register(ExporterSpec('custom', ('.custom',), writer, supports_image_source_rects=True))
    report = capable.write(model, output)
    assert report.success and output.read_bytes() == b'own handled output', report.issues
    assert calls == [RECT]


@pytest.mark.parametrize('value', [0, 1, None, 'yes'])
def test_capability_requires_boolean(value):
    with pytest.raises(ValueError, match='supports_image_source_rects must be bool'):
        ExporterSpec('custom', ('.custom',), lambda doc, path: od.ConversionReport(path), supports_image_source_rects=value)
