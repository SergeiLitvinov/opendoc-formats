"""Physical OPC components survive the semantic adapter, JSON and actual package emission."""

import io
import zipfile
from dataclasses import replace
from threading import Event

import pytest
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    Image,
    PreservationState,
    document_from_json,
    document_to_json,
    get_integration,
)

from opendoc_formats import read_document, write_document
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError
from opendoc_formats.ooxml.orphans import KEY
from opendoc_formats.readers.docx import read_docx_model
from tests.binary_fixtures import PR, RGB, W, own_docx, own_png, zip_bytes


def entries(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def source_bytes(*, linked=False, collision=False, custom_root=False):
    values = entries(own_docx())
    types = values['[Content_Types].xml'].decode()
    types = types.replace('</Types>', '<Default Extension="xml" ContentType="application/xml"/></Types>')
    values['[Content_Types].xml'] = types.encode()
    if collision:
        values['word/media/image1.png'] = values.pop('word/media/own.png')
        values['word/_rels/document.xml.rels'] = values['word/_rels/document.xml.rels'].replace(
            b'media/own.png', b'media/image1.png')
        values['word/settings.xml'] = b'<private xmlns="urn:own">Own settings-name collision</private>'
    if linked:
        image = 'image1.png' if collision else 'own.png'
        values['private/first.xml'] = b'<own xmlns="urn:own">Own first component</own>'
        values['private/second.bin'] = b'Own cyclic binary\x00\xff'
        values['private/_rels/first.xml.rels'] = (
            f'<Relationships xmlns="{PR}" xmlns:own="urn:own" own:marker="keep">'
            f'<Relationship Id="b" Type="urn:own:binary" Target="second.bin"/>'
            f'<Relationship Id="image" Type="urn:own:image" Target="../word/media/{image}#own-fragment"/>'
            '<Relationship Id="external" Type="urn:own:external" Target="https://example.invalid/own" TargetMode="External"/>'
            '</Relationships>'
        ).encode()
        values['private/_rels/second.bin.rels'] = (
            f'<Relationships xmlns="{PR}"><Relationship Id="cycle" Type="urn:own:cycle" Target="first.xml"/></Relationships>'
        ).encode('utf-16')
    if custom_root:
        values['custom/main.xml'] = values.pop('word/document.xml')
        values['_rels/.rels'] = values['_rels/.rels'].replace(b'word/document.xml', b'custom/main.xml')
        values['[Content_Types].xml'] = values['[Content_Types].xml'].replace(b'/word/document.xml', b'/custom/main.xml')
        values['custom/_rels/main.xml.rels'] = values.pop('word/_rels/document.xml.rels').replace(
            b'Target="media/', b'Target="../word/media/')
        if linked:
            values['private/_rels/first.xml.rels'] = values['private/_rels/first.xml.rels'].replace(
                b'</Relationships>', b'<Relationship Id="main" Type="urn:own:main" Target="../custom/main.xml"/></Relationships>')
    return zip_bytes(list(values.items()))


@pytest.mark.parametrize('linked,collision,custom_root', [(False, False, False), (True, False, False),
                                                       (True, True, False), (True, False, True)])
def test_all_unreachable_parts_and_dependency_payloads_survive_two_actual_docx_json_cycles(
    tmp_path, linked, collision, custom_root,
):
    source = tmp_path/'source.docx'
    original = source_bytes(linked=linked, collision=collision, custom_root=custom_root)
    source.write_bytes(original)
    model = read_docx_model(source)
    selected = model.metadata[KEY]['parts']
    original_parts = entries(original)
    assert '/word/embeddings/unknown.bin' in selected
    if linked:
        assert '/private/_rels/second.bin.rels' in selected
        assert '/word/media/'+('image1.png' if collision else 'own.png') in selected
    records = [record for record in get_integration(model).preservation if record.issue.code == 'docx.orphan-part']
    assert len(records) == len(selected)
    assert all(record.state is PreservationState.OPAQUE and record.provenance.source_path == str(source) for record in records)
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        if cycle == 0:
            model.sections[0].blocks[0].content[0].text = 'Own edited body'
        output = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(model, output)
        assert report.success, [(getattr(issue, "code", getattr(issue, "feature", "")), issue.message) for issue in report.issues]
        saved = entries(output.read_bytes())
        for name in selected:
            assert saved[name[1:]] == original_parts[name[1:]], name
        assert b'Own edited body' in saved['custom/main.xml' if custom_root else 'word/document.xml']
        assert b'private/' not in saved['custom/_rels/main.xml.rels' if custom_root else 'word/_rels/document.xml.rels']
        model = read_docx_model(output)
    assert source.read_bytes() == original


def test_semantic_image_edit_does_not_overwrite_the_opaque_dependency_at_its_source_uri(tmp_path):
    source = tmp_path/'source.docx'
    source.write_bytes(source_bytes(linked=True, collision=True))
    model = read_docx_model(source)
    new_png = own_png(RGB[::-1])
    from opendoc_model import walk_model

    image = next(ref.node for ref in walk_model(model) if isinstance(ref.node, Image))
    model.resources[image.resource_id].data = new_png
    output = tmp_path/'edited.docx'
    result = write_document(model, output)
    assert result.success, [(getattr(issue, "code", getattr(issue, "feature", "")), issue.message) for issue in result.issues]
    saved = entries(output.read_bytes())
    assert saved['word/media/image1.png'] == own_png()
    assert any(value == new_png for name, value in saved.items() if name.startswith('word/media/'))
    parsed = read_docx_model(output)
    assert any(resource.data == new_png for resource in parsed.resources.values())


def test_dependency_closure_retains_reachable_xml_with_its_own_relationships(tmp_path):
    parts = entries(source_bytes(linked=True))
    parts['word/styles.xml'] = f'<w:styles xmlns:w="{W}"/>'.encode('utf-16')
    parts['word/_rels/styles.xml.rels'] = (
        f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own:child" '
        'Target="native-child.bin"/></Relationships>'
    ).encode()
    parts['word/native-child.bin'] = b'Own reachable dependency binary'
    parts['word/_rels/document.xml.rels'] = parts['word/_rels/document.xml.rels'].replace(
        b'</Relationships>',
        b'<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        b'Target="styles.xml"/></Relationships>')
    parts['[Content_Types].xml'] = parts['[Content_Types].xml'].replace(
        b'</Types>', b'<Override PartName="/word/styles.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    parts['private/_rels/first.xml.rels'] = parts['private/_rels/first.xml.rels'].replace(
        b'</Relationships>',
        b'<Relationship Id="styles" Type="urn:own:styles" Target="../word/styles.xml"/></Relationships>')
    source = tmp_path/'source.docx'
    original = zip_bytes(list(parts.items()))
    source.write_bytes(original)
    model = read_docx_model(source)
    selected = model.metadata[KEY]['parts']
    assert '/word/styles.xml' in selected and '/word/_rels/styles.xml.rels' in selected
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        output = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(model, output)
        assert report.success, report.issues
        saved = entries(output.read_bytes())
        assert all(saved[name[1:]] == parts[name[1:]] for name in selected)
        model = read_docx_model(output)
    assert source.read_bytes() == original


def test_opaque_graph_edit_is_authoritative_not_replaced_from_a_stale_source_copy(tmp_path):
    source = tmp_path/'source.docx'
    source.write_bytes(source_bytes())
    model = read_docx_model(source)
    name = '/word/embeddings/unknown.bin'
    model.package.parts[name] = replace(model.package.parts[name], data=b'Own intentional native edit')
    output = tmp_path/'edited.docx'
    assert write_document(model, output).success
    assert entries(output.read_bytes())[name[1:]] == b'Own intentional native edit'


@pytest.mark.parametrize('name', ['word/styles.xml', 'word/settings.xml', 'docProps/core.xml'])
def test_lazy_backend_defaults_do_not_hide_an_original_unreferenced_part(tmp_path, name):
    parts = entries(source_bytes())
    parts[name] = b'<own xmlns="urn:own">Unreferenced original, not a generated default</own>'
    source = tmp_path/'source.docx'
    original = zip_bytes(list(parts.items()))
    source.write_bytes(original)
    model = read_docx_model(source)
    assert '/'+name in model.metadata[KEY]['roots']
    for cycle in range(2):
        model = document_from_json(document_to_json(model))
        output = tmp_path/f'cycle-{cycle}.docx'
        report = write_document(model, output)
        assert report.success, report.issues
        saved = entries(output.read_bytes())
        assert saved[name] == parts[name]
        model = read_docx_model(output)
        assert '/'+name in model.metadata[KEY]['roots']
    assert source.read_bytes() == original


@pytest.mark.parametrize('change', ['missing', 'version', 'new-dangling-target', 'graph-none', 'wrong-format', 'binding-none'])
def test_invalidated_native_bindings_preserve_existing_destination_and_model(tmp_path, change):
    source = tmp_path/'source.docx'
    source.write_bytes(source_bytes(linked=True))
    model = read_docx_model(source)
    if change == 'missing':
        del model.package.parts['/word/embeddings/unknown.bin']
    elif change == 'version':
        model.metadata[KEY]['version'] = 2
    elif change == 'graph-none':
        model.package = None
    elif change == 'wrong-format':
        model.package.format = 'other'
    elif change == 'binding-none':
        model.metadata[KEY] = None
    else:
        name = '/private/_rels/first.xml.rels'
        model.package.parts[name] = replace(model.package.parts[name], data=model.package.parts[name].data.replace(
            b'second.bin', b'missing.bin'))
    before = document_to_json(model)
    output = tmp_path/'existing.docx'
    output.write_bytes(b'Own existing destination')
    report = write_document(model, output)
    assert not report.success and output.read_bytes() == b'Own existing destination'
    assert document_to_json(model) == before


@pytest.mark.parametrize('target', ['missing.bin', '../../escape.bin', 'https://example.invalid/file'])
def test_invalid_source_component_target_is_rejected_without_changing_source(tmp_path, target):
    data = entries(source_bytes(linked=True))
    data['private/_rels/first.xml.rels'] = data['private/_rels/first.xml.rels'].replace(b'second.bin', target.encode())
    source = tmp_path/'source.docx'
    source.write_bytes(zip_bytes(list(data.items())))
    original = source.read_bytes()
    with pytest.raises(InvalidDocumentError):
        read_docx_model(source)
    assert source.read_bytes() == original


def test_opaque_payload_limit_is_checked_before_reading_the_orphan_bytes(tmp_path, monkeypatch):
    data = entries(source_bytes())
    data['word/embeddings/unknown.bin'] = b'Own limit'*1000
    source = tmp_path/'source.docx'
    source.write_bytes(zip_bytes(list(data.items())))
    original = source.read_bytes()
    open_member = zipfile.ZipFile.open

    def checked(self, name, *args, **kwargs):
        member = name.filename if isinstance(name, zipfile.ZipInfo) else name
        assert member != 'word/embeddings/unknown.bin', 'Over-budget orphan was read'
        return open_member(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, 'open', checked)
    with pytest.raises(ArtifactLimitError) as captured:
        read_docx_model(source, limits=DocumentLimits(max_embedded_bytes=1000))
    assert captured.value.path == "package.parts['/word/embeddings/unknown.bin']"
    assert source.read_bytes() == original


def test_cancel_inside_component_closure_does_not_return_a_partial_model(tmp_path, monkeypatch):
    from opendoc_formats.ooxml import orphans

    source = tmp_path/'source.docx'
    source.write_bytes(source_bytes(linked=True))
    original, stop = source.read_bytes(), Event()
    targets = orphans._targets

    def first(*args, **kwargs):
        result = targets(*args, **kwargs)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(orphans, '_targets', first)
        with pytest.raises(OperationCancelledError):
            read_docx_model(source, cancelled=stop.is_set)
    assert source.read_bytes() == original
    assert read_document(source).success


def test_capture_uses_the_same_source_snapshot_as_the_semantic_parser(tmp_path, monkeypatch):
    import hashlib

    import docx

    source = tmp_path/'source.docx'
    original = source_bytes(linked=True)
    changed = source_bytes(linked=False)
    source.write_bytes(original)
    load = docx.Document

    def loaded(data):
        document = load(data)
        source.write_bytes(changed)  # simulate an external writer after the snapshot was read
        return document

    monkeypatch.setattr(docx, 'Document', loaded)
    model = read_docx_model(source)
    assert model.metadata[KEY]['source_sha256'] == hashlib.sha256(original).hexdigest()
    assert '/private/first.xml' in model.package.parts
    assert source.read_bytes() == changed


def test_late_cancellation_after_detached_payloads_keeps_destination_and_input(tmp_path, monkeypatch):
    from opendoc_formats.ooxml import orphans
    from opendoc_formats.writers.docx_writer import write_docx_model

    source = tmp_path/'source.docx'
    source.write_bytes(source_bytes(linked=True))
    model = read_docx_model(source)
    before = document_to_json(model)
    output = tmp_path/'existing.docx'
    output.write_bytes(b'Own prior destination')
    stop, calls = Event(), []
    restore = orphans.restore_detached_parts

    def restored(*args, **kwargs):
        restore(*args, **kwargs)
        calls.append(True)
        stop.set()

    monkeypatch.setattr(orphans, 'restore_detached_parts', restored)
    with pytest.raises(OperationCancelledError):
        write_docx_model(model, output, cancelled=stop.is_set)
    assert calls == [True] and output.read_bytes() == b'Own prior destination'
    assert document_to_json(model) == before


def test_inactive_callback_keeps_all_package_member_payloads(tmp_path):
    from opendoc_formats.writers.docx_writer import write_docx_model

    source = tmp_path/'source.docx'
    source.write_bytes(source_bytes(linked=True, collision=True))
    model = read_docx_model(source)
    before = document_to_json(model)
    first, second = tmp_path/'first.docx', tmp_path/'second.docx'
    assert write_docx_model(model, first).success
    assert write_docx_model(model, second, cancelled=lambda: False).success
    assert entries(first.read_bytes()) == entries(second.read_bytes())
    assert document_to_json(model) == before


@pytest.mark.parametrize('xml', [
    f'<Relationships xmlns="{PR}"><Relationship Id="same" Type="urn:own" Target="second.bin"/>'
    '<Relationship Id="same" Type="urn:own" Target="second.bin"/></Relationships>',
    f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" Target="second.bin" '
    'TargetMode="Unknown"/></Relationships>',
    f'<Relationships xmlns="{PR}"><Relationship Id="own" Target="second.bin"/></Relationships>',
])
def test_malformed_unreachable_relationships_are_not_silently_retained_as_valid(tmp_path, xml):
    parts = entries(source_bytes(linked=True))
    parts['private/_rels/first.xml.rels'] = xml.encode('utf-16')
    source = tmp_path/'source.docx'
    original = zip_bytes(list(parts.items()))
    source.write_bytes(original)
    with pytest.raises(InvalidDocumentError):
        read_docx_model(source)
    assert source.read_bytes() == original


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_unreachable_relationship_dtd_is_rejected_before_entity_expansion(tmp_path, encoding):
    from opendoc_formats.errors import UnsupportedDocumentError

    parts = entries(source_bytes(linked=True))
    parts['private/_rels/first.xml.rels'] = (
        '<!DOCTYPE Relationships [<!ENTITY own "second.bin">]>'
        f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" Target="&own;"/></Relationships>'
    ).encode(encoding)
    source = tmp_path/'source.docx'
    original = zip_bytes(list(parts.items()))
    source.write_bytes(original)
    with pytest.raises(UnsupportedDocumentError, match='DTD/entities'):
        read_docx_model(source)
    assert source.read_bytes() == original


def test_cancel_during_detached_zip_copy_keeps_destination_and_cleans_intermediate(tmp_path, monkeypatch):
    from opendoc_formats.writers.docx_writer import write_docx_model

    source = tmp_path/'source.docx'
    original = source_bytes(linked=True)
    source.write_bytes(original)
    model = read_docx_model(source)
    before = document_to_json(model)
    output = tmp_path/'existing.docx'
    output.write_bytes(b'Own prior destination')
    stop, reads, intermediates = Event(), [], []
    read = zipfile.ZipExtFile.read
    open_member = zipfile.ZipFile.open

    def opened(self, name, mode='r', *args, **kwargs):
        result = open_member(self, name, mode, *args, **kwargs)
        if mode == 'w' and str(self.filename).endswith('.detached.docx'):
            from pathlib import Path

            intermediates.append(Path(self.filename))
        return result

    def copied(self, *args, **kwargs):
        value = read(self, *args, **kwargs)
        if value and intermediates:
            reads.append(self.name)
            stop.set()
        return value

    monkeypatch.setattr(zipfile.ZipExtFile, 'read', copied)
    monkeypatch.setattr(zipfile.ZipFile, 'open', opened)
    with pytest.raises(OperationCancelledError):
        write_docx_model(model, output, cancelled=stop.is_set)
    assert reads and output.read_bytes() == b'Own prior destination'
    assert source.read_bytes() == original and document_to_json(model) == before
    assert intermediates and all(not path.exists() for path in intermediates)
    assert not list(tmp_path.rglob('*.detached.docx'))
    assert not list(tmp_path.rglob('*.partial*'))
