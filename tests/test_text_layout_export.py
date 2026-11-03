"""No silent layout loss, including forward data retained by the official older Model."""

from pathlib import Path

import opendoc_model as od
import pytest

from opendoc_formats.export import ExporterRegistry, ExporterSpec, default_exporter_registry, write_document


def layout_document():
    return od.load_document(Path(__file__).parent/'native'/'data'/'text-layout-v1.json')


@pytest.mark.parametrize('suffix', ['.txt', '.html', '.epub', '.docx', '.pptx', '.pdf', '.tex'])
@pytest.mark.parametrize('existing', [False, True])
def test_builtin_writers_reject_unprojected_layout_before_backend_or_destination_changes(tmp_path, monkeypatch, suffix, existing):
    import opendoc_formats.export as module

    document = layout_document()
    before = od.document_to_json(document)
    output = tmp_path/'new-parent'/'target'
    output = output.with_suffix(suffix)
    if existing:
        output.parent.mkdir()
        output.write_bytes(b'Existing destination')

    def forbidden(*args, **kwargs):
        pytest.fail('Backend lookup or writer called for unprojected text layouts')

    monkeypatch.setattr(module, 'missing_backends', forbidden)
    registry = default_exporter_registry()
    result = registry.write(document, output)
    assert not result.success
    issue, = result.issues
    assert issue.feature == 'export.text-layout' and issue.severity == od.IssueSeverity.ERROR
    assert 'text_layouts' in issue.location
    assert od.document_to_json(document) == before
    if existing:
        assert output.read_bytes() == b'Existing destination'
        assert list(output.parent.iterdir()) == [output]
    else:
        assert not output.parent.exists()


def test_json_preserves_layout_registry_through_two_actual_exports(tmp_path):
    document = layout_document()
    expected = od.integration_to_dict(od.get_integration(document))
    for index in range(2):
        path = tmp_path/f'cycle-{index}.json'
        result = write_document(document, path)
        assert result.success
        document = od.load_document(path)
        assert od.integration_to_dict(od.get_integration(document)) == expected


def test_custom_exporter_must_explicitly_declare_layout_support(tmp_path):
    document = layout_document()
    calls = []

    def writer(model, path):
        calls.append(path)
        od.save_document(model, path)
        return od.ConversionReport(path)

    output = tmp_path/'saved.custom'
    registry = ExporterRegistry()
    registry.register(ExporterSpec('custom', ('.custom',), writer))
    assert not registry.write(document, output).success and not calls and not output.exists()
    capable = ExporterRegistry()
    capable.register(ExporterSpec('custom', ('.custom',), writer, supports_text_layouts=True))
    assert capable.write(document, output).success and len(calls) == 1
    restored = od.load_document(output)
    assert od.integration_to_dict(od.get_integration(restored)) == od.integration_to_dict(od.get_integration(document))


@pytest.mark.parametrize('value', [1, 0, 'yes', None])
def test_layout_support_declaration_requires_boolean(value):
    with pytest.raises(ValueError, match='supports_text_layouts must be bool'):
        ExporterSpec('custom', ('.custom',), lambda document, path: od.ConversionReport(path), supports_text_layouts=value)


def test_empty_forward_registry_does_not_block_an_ordinary_document(tmp_path):
    document = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([od.TextRun('Own')])])])
    # On Model releases with typed layouts this is normalized into the empty typed registry.
    envelope = od.integration_to_dict(od.IntegrationModel())
    envelope['data']['text_layouts'] = []
    od.set_integration(document, od.integration_from_dict(envelope))
    output = tmp_path/'own.txt'
    assert write_document(document, output).success and output.read_bytes() == b'Own'
