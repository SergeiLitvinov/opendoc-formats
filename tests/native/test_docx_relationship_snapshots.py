"""Immutable native relationship facts with physical owners and bounded per-object inventory."""

import io
import zipfile
from dataclasses import FrozenInstanceError, replace
from threading import Event

import pytest

from opendoc_formats.docx import DocxLimits, DocxPackage, RelationshipSnapshot, ReplaceTextSpan
from opendoc_formats.errors import DocumentClosedError, InvalidDocumentError, OperationCancelledError, ResourceLimitError
from tests.binary_fixtures import PR, zip_bytes
from tools.docx_native_smoke import source_package


def source(*, orphan=False):
    with zipfile.ZipFile(io.BytesIO(source_package())) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    relationships = (f'<Relationships xmlns="{PR}" xmlns:future="urn:future">'
        '<Relationship Id="own" Type="urn:own" Target="../custom/target.xml" future:flag="value"/>'
        '<Relationship Id="external" Type="urn:link" Target="https://example.invalid/%FF" TargetMode="External"/>'
        '</Relationships>').encode()
    name = 'word/_rels/missing%20part.xml.rels' if orphan else 'word/_rels/document.xml.rels'
    parts[name] = relationships
    parts['custom/target.xml'] = b'<own/>'
    if orphan:
        parts['word/missing part.xml'] = b'<other/>'  # A similar decoded spelling is not a proven physical owner.
    return zip_bytes(list(parts.items()))


def test_inventory_has_source_fields_namespace_attributes_and_distinct_external_status():
    data = source()
    with DocxPackage(data) as package:
        root, internal, external = package.relationships
        assert isinstance(root, RelationshipSnapshot)
        assert root.part == '_rels/.rels' and root.index == 0 and root.owner_status == 'package'
        assert root.source_part is None and root.nominal_source_part is None and root.target_part == 'word/document.xml'
        assert internal.part == 'word/_rels/document.xml.rels' and internal.index == 0 and internal.id == 'own'
        assert internal.type == 'urn:own' and internal.target == '../custom/target.xml'
        assert internal.source_part == 'word/document.xml' and internal.owner_status == 'part'
        assert internal.nominal_source_part == internal.source_part and internal.target_part == 'custom/target.xml'
        assert internal.target_mode == 'Internal' and 'TargetMode' not in dict(internal.attributes)
        assert dict(internal.attributes)['{urn:future}flag'] == 'value'
        assert external.index == 1 and external.target_mode == 'External' and external.target_part is None
        assert external.target == 'https://example.invalid/%FF' and dict(external.attributes)['TargetMode'] == 'External'
        assert package.to_bytes() == data


def test_snapshot_is_independent_immutable_and_closed_context_refuses_access():
    with DocxPackage(source()) as package:
        facts = package.relationships
        with pytest.raises(FrozenInstanceError):
            facts[0].target = 'different'
        changed = package.to_bytes([ReplaceTextSpan(package.paragraphs[0].id, 0, 3, 'Edited')])
        assert package.relationships == facts
        with DocxPackage(changed) as edited:
            assert edited.relationships == facts
    assert facts[0].target_part == 'word/document.xml'
    with pytest.raises(DocumentClosedError):
        _ = package.relationships


def test_xml_child_indices_keep_comment_and_processing_instruction_positions():
    with zipfile.ZipFile(io.BytesIO(source())) as archive:
        parts = [(name, archive.read(name)) for name in archive.namelist()]
    parts = [(name, value.replace(b'xmlns:future="urn:future">',
              b'xmlns:future="urn:future"><!--own--><?own inert?>')
              if name == 'word/_rels/document.xml.rels' else value) for name, value in parts]
    data = zip_bytes(parts)
    with DocxPackage(data, limits=replace(DocxLimits(), max_relationships=3)) as package:
        assert [row.index for row in package.relationships] == [0, 2, 3]
        assert package.to_bytes() == data


def test_orphan_relationships_do_not_inherit_a_similarly_named_physical_owner():
    data = source(orphan=True)
    with pytest.raises(InvalidDocumentError, match='missing source part'):
        DocxPackage(data)
    with DocxPackage(data, inspection_only=True) as package:
        assert len(package.info.issues) == 1 and len(package.relationships) == 3
        _, internal, external = package.relationships
        assert internal.owner_status == external.owner_status == 'missing'
        assert internal.nominal_source_part == 'word/missing%20part.xml'
        assert internal.source_part is None and internal.target_part is None and external.target_part is None
        assert internal.target == '../custom/target.xml' and package.to_bytes() == data


def test_literal_percent_owner_is_preserved_without_decoding_its_physical_name_again():
    from tests.native.test_docx_uri_aliases import package as aliased_package

    rels = (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" '
            'Target="../custom/target.xml"/></Relationships>').encode()
    data = aliased_package('word/own%2F.xml', 'word/own%252F.xml', '/word/own%252F.xml', extra=[
        ('word/_rels/own%2F.xml.rels', rels), ('custom/target.xml', b'<own/>')])
    with DocxPackage(data) as package:
        _, relationship = package.relationships
        assert relationship.source_part == 'word/own%2F.xml' and relationship.owner_status == 'part'
        assert relationship.target_part == 'custom/target.xml' and package.to_bytes() == data


def test_relationship_work_quota_is_shared_by_package_and_part_relationships(tmp_path):
    data = source()
    path = tmp_path/'own.docx'
    path.write_bytes(data)
    with DocxPackage(path, limits=replace(DocxLimits(), max_relationships=3)) as package:
        assert len(package.relationships) == 3
    with pytest.raises(ResourceLimitError, match=r'word/_rels/document.xml.rels.*max_relationships'):
        DocxPackage(path, limits=replace(DocxLimits(), max_relationships=2))
    assert path.read_bytes() == data


def test_cancellation_between_relationship_snapshots_keeps_source_and_scope(tmp_path, monkeypatch):
    from opendoc_formats.native import docx_package

    data = source()
    path = tmp_path/'own.docx'
    path.write_bytes(data)
    stop = Event()
    original = docx_package.RelationshipSnapshot

    def cancelled(*args, **kwargs):
        result = original(*args, **kwargs)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(docx_package, 'RelationshipSnapshot', cancelled)
        with pytest.raises(OperationCancelledError):
            DocxPackage(path, cancelled=stop.is_set)
    assert path.read_bytes() == data
    with DocxPackage(path) as package:
        assert len(package.relationships) == 3
