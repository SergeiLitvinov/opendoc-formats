"""Physical OPC edges and gaps are evidenced without fetching targets or repairing files."""

import io
import json
import zipfile
from dataclasses import FrozenInstanceError
from threading import Event

import pytest

from opendoc_formats.anatomy import compare_snapshots, inspect_binary
from opendoc_formats.errors import OperationCancelledError
from tests.binary_fixtures import PR, own_docx, zip_bytes


def parts():
    with zipfile.ZipFile(io.BytesIO(own_docx())) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def links(*targets):
    return (f'<Relationships xmlns="{PR}">'+''.join(
        f'<Relationship Id="id{index}" Type="urn:own" Target="{target}"/>'
        for index, target in enumerate(targets))+'</Relationships>').encode()


def snapshot(values):
    return inspect_binary(zip_bytes(list(values.items())), capture=True)


def test_original_ownership_root_default_content_type_and_unreachable_binary():
    source = own_docx()
    result = inspect_binary(source, capture=True)
    audit = result.opc
    assert audit is not None and audit.reachability_complete and not audit.findings
    assert audit.reachable_parts == ('/word/document.xml', '/word/media/own.png')
    assert audit.unreachable_parts == audit.unreached_parts == ('/word/embeddings/unknown.bin',)
    assert audit.relationships[0].owner == '/'
    root = next(item for item in result.items if item.locator == 'zip:/_rels/.rels')
    assert dict(root.details)['content_type'] == 'application/vnd.openxmlformats-package.relationships+xml'
    assert dict(root.details)['xml_detection'] == 'opc-content-type'
    external = audit.relationships[-1]
    assert external.status == 'external' and external.resolved_target is None
    assert dict(external.attributes)['Target'] == 'https://example.invalid/own'
    assert audit.relationships[0].location == 'zip:/_rels/.rels#xml:0/0'
    assert json.loads(json.dumps(result.to_dict()))['opc']['assessment_complete'] is False
    detached = result.to_dict()
    detached['opc']['relationships'][0]['attributes']['Target'] = 'tampered'
    assert dict(audit.relationships[0].attributes)['Target'] == 'word/document.xml'
    with pytest.raises(FrozenInstanceError):
        audit.reachability_complete = False
    assert inspect_binary(source).source_sha256 == result.source_sha256


def test_disconnected_cycles_and_multiple_paths_have_bounded_literal_reachability():
    values = parts()
    values['private/a.bin'], values['private/b.bin'] = b'Own A', b'Own B'
    values['private/_rels/a.bin.rels'] = links('b.bin', '../word/media/own.png#own-fragment')
    values['private/_rels/b.bin.rels'] = links('a.bin')
    result = snapshot(values)
    assert result.opc.reachability_complete
    assert '/private/a.bin' in result.opc.unreachable_parts and '/private/b.bin' in result.opc.unreachable_parts
    edge = next(edge for edge in result.opc.relationships if dict(edge.attributes).get('Target', '').endswith('#own-fragment'))
    assert edge.resolved_target == '/word/media/own.png'
    values['_rels/.rels'] = links('word/document.xml', 'private/a.bin', 'private/a.bin')
    connected = snapshot(values)
    assert connected.opc.reachability_complete and '/private/b.bin' in connected.opc.reachable_parts
    assert '/private/a.bin' not in connected.opc.unreachable_parts
    assert compare_snapshots(result, connected)['opc_changed']


@pytest.mark.parametrize('target,code', [
    ('missing.bin', 'opc.target-missing-or-infrastructure'),
    ('../../../escape.bin', 'opc.target-invalid'),
    ('https://example.invalid/own', 'opc.target-invalid'),
    ('%2e%2e/escape.bin', 'opc.target-invalid'),
    ('../_rels/.rels', 'opc.target-missing-or-infrastructure'),
])
def test_bad_internal_target_keeps_raw_evidence_and_never_claims_definite_unreachability(target, code):
    values = parts()
    values['word/_rels/document.xml.rels'] = links(target)
    result = snapshot(values)
    assert not result.opc.reachability_complete and not result.opc.unreachable_parts
    assert '/word/media/own.png' in result.opc.unreached_parts
    finding = next(finding for finding in result.opc.findings if finding.code == code)
    assert finding.location == 'zip:/word/_rels/document.xml.rels#xml:0/0'
    item = next(item for item in result.items if item.locator == 'zip:/word/_rels/document.xml.rels')
    assert item.payload == values['word/_rels/document.xml.rels']


def test_missing_relationship_owner_is_a_located_gap_in_the_forensic_inventory():
    values = parts()
    values['private/_rels/absent.bin.rels'] = links('../word/media/own.png')
    result = snapshot(values)
    assert not result.opc.reachability_complete
    finding = next(finding for finding in result.opc.findings if finding.code == 'opc.owner-missing')
    assert finding.location == 'zip:/private/_rels/absent.bin.rels'
    assert any(edge.owner == '/private/absent.bin' and edge.status == 'rejected' for edge in result.opc.relationships)


@pytest.mark.parametrize('xml,code', [
    ('<wrong/>', 'opc.relationship-root'),
    (f'<Relationships xmlns="{PR}"><Relationship Id="own" Target="media/own.png"/></Relationships>',
     'opc.relationship-attributes'),
    (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" Target="media/own.png" '
     'TargetMode="Unexpected"/></Relationships>', 'opc.target-mode'),
    (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" Target="media/own.png"/>'
     '<Relationship Id="own" Type="urn:own" Target="media/own.png"/></Relationships>', 'opc.relationship-attributes'),
    (f'<Relationships xmlns="{PR}"><own xmlns="urn:own"/></Relationships>', 'opc.relationship-extension'),
])
def test_relationship_gaps_are_reported_without_converting_the_source_to_a_successful_import(xml, code):
    values = parts()
    values['word/_rels/document.xml.rels'] = xml.encode('utf-16')
    result = snapshot(values)
    assert code in {finding.code for finding in result.opc.findings}
    assert not result.opc.reachability_complete and result.opc.unreachable_parts == ()


def test_content_type_gaps_and_absent_root_are_explicit():
    values = parts()
    del values['_rels/.rels']
    values['private/no-type'] = b'Own unknown bytes'
    values['[Content_Types].xml'] = values['[Content_Types].xml'].replace(
        b'</Types>', b'<Override PartName="/private/missing.bin" ContentType="application/octet-stream"/></Types>')
    result = snapshot(values)
    codes = {finding.code for finding in result.opc.findings}
    assert {'opc.content-type-missing', 'opc.override-target-missing', 'opc.root-unavailable'} <= codes
    assert not result.opc.reachable_parts and not result.opc.unreachable_parts


def test_declared_binary_relationship_payload_is_not_forced_through_xml():
    values = parts()
    values['[Content_Types].xml'] = values['[Content_Types].xml'].replace(
        b'</Types>', b'<Override PartName="/word/_rels/document.xml.rels" ContentType="application/octet-stream"/></Types>')
    values['word/_rels/document.xml.rels'] = b'Own binary\x00\xff'
    result = snapshot(values)
    assert {'opc.relationship-content-type', 'opc.relationship-uninspected'} <= {
        finding.code for finding in result.opc.findings}
    assert result.opc.unreachable_parts == ()


def test_binary_data_named_rels_outside_relationship_directory_remains_a_data_part():
    values = parts()
    values['private/own.rels'] = b'Own binary\x00\xff'
    values['[Content_Types].xml'] = values['[Content_Types].xml'].replace(
        b'</Types>', b'<Override PartName="/private/own.rels" ContentType="application/octet-stream"/></Types>')
    result = snapshot(values)
    assert result.opc.reachability_complete
    assert '/private/own.rels' in result.opc.unreachable_parts


def test_raw_zip_and_opaque_mode_do_not_claim_an_opc_audit():
    assert inspect_binary(zip_bytes([('own.bin', b'Own bytes')])).opc is None
    assert inspect_binary(own_docx(), parse_xml=False).opc is None


def test_wire_entry_reordering_does_not_create_a_false_graph_change():
    values = parts()
    original = snapshot(values)
    reordered = inspect_binary(zip_bytes(list(reversed(list(values.items())))))
    assert original.opc == reordered.opc
    assert not compare_snapshots(original, reordered)['opc_changed']


def test_invalid_typed_relationship_address_is_located_and_strict_import_still_rejects(tmp_path):
    from opendoc_formats.errors import InvalidDocumentError
    from opendoc_formats.readers.docx import read_docx_model

    values = parts()
    values['private/_rels/.rels'] = links('../word/document.xml')
    source = tmp_path/'own.docx'
    original = zip_bytes(list(values.items()))
    source.write_bytes(original)
    result = inspect_binary(source)
    assert 'opc.owner-address-invalid' in {finding.code for finding in result.opc.findings}
    with pytest.raises(InvalidDocumentError, match='relationship part has no owner address'):
        read_docx_model(source)
    assert source.read_bytes() == original


def test_cancel_during_target_resolution_prevents_the_next_relationship(monkeypatch):
    import opendoc_formats.native.opc_audit as audit

    stop, calls = Event(), []
    resolve = audit.resolve_target

    def first(*args):
        assert not calls, 'Another internal relationship was resolved after cancellation'
        calls.append(True)
        result = resolve(*args)
        stop.set()
        return result

    monkeypatch.setattr(audit, 'resolve_target', first)
    with pytest.raises(OperationCancelledError):
        inspect_binary(own_docx(), cancelled=stop.is_set)
    assert calls == [True]
