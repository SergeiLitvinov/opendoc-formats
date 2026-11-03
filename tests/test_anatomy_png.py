"""Own PNG wire originals: physical layout, not a replacement pixel decoder."""

import builtins
import hashlib
import io
import json
import struct
import sys
import zlib
from dataclasses import replace
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.anatomy_tree import inspect_container_tree
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.binary_fixtures import own_png, zip_bytes
from tools.document_anatomy import main

SIGNATURE = b'\x89PNG\r\n\x1a\n'


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def header(width=2, height=2, depth=8, color=2, compression=0, filtering=0, interlace=0):
    return chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, compression, filtering, interlace))


def wire(*chunks):
    return SIGNATURE + b''.join(chunks)


def test_real_rgb_original_chunks_reassemble_exactly_with_header_dimensions():
    source = own_png()
    snapshot = inspect_binary(source, capture=True)
    assert snapshot.container == 'png' and snapshot.opc is snapshot.epub is None
    assert b''.join(item.payload for item in snapshot.items) == source
    assert [item.locator for item in snapshot.items] == ['png:signature', 'png:chunk=0:IHDR',
                                                       'png:chunk=1:IDAT', 'png:chunk=2:IEND']
    for item in snapshot.items:
        assert item.size == len(item.payload) and item.sha256 == hashlib.sha256(item.payload).hexdigest()
        if item.kind == 'png-chunk':
            detail = dict(item.details)
            assert source[detail['offset']:detail['offset'] + item.size] == item.payload
            assert detail['crc_verified']
    details = dict(snapshot.details)
    assert (details['width'], details['height'], details['bit_depth'], details['color_type']) == (2, 2, 8, 2)
    assert not details['image_data_assessed'] and not details['assessment_complete']
    assert inspect_binary(source, container='png').to_dict() == snapshot.to_dict()


@pytest.mark.parametrize('mode,value,depth,color', [('RGB', (1, 2, 3), 8, 2), ('RGBA', (1, 2, 3, 4), 8, 6),
                                                  ('L', 77, 8, 0), ('P', 0, 8, 3), ('I;16', 512, 16, 0)])
def test_independent_pillow_originals_confirm_dimensions_and_unchanged_pixels(mode, value, depth, color):
    image_module = pytest.importorskip('PIL.Image')
    with image_module.new(mode, (2, 3), value) as original:
        if mode == 'P':
            original.putpalette([channel for entry in range(256) for channel in (entry, 255 - entry, 0)])
        output = io.BytesIO()
        original.save(output, format='PNG')
    source = output.getvalue()
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert (details['width'], details['height'], details['bit_depth'], details['color_type']) == (2, 3, depth, color)
    assert b''.join(item.payload for item in snapshot.items) == source
    with image_module.open(io.BytesIO(source)) as decoded:
        assert decoded.size == (2, 3) and decoded.getpixel((0, 0)) == value


@pytest.mark.parametrize('color,depth', [(0, 1), (0, 2), (0, 4), (0, 8), (0, 16),
                                       (2, 8), (2, 16), (3, 1), (3, 2), (3, 4), (3, 8),
                                       (4, 8), (4, 16), (6, 8), (6, 16)])
@pytest.mark.parametrize('interlace', [0, 1])
def test_all_ihdr_depth_color_profiles_are_physical_observations(color, depth, interlace):
    chunks = [header(color=color, depth=depth, interlace=interlace)]
    if color == 3:
        chunks.append(chunk(b'PLTE', b'\x00\x01\x02' * 2))
    # Intentionally not pixel data: this inspector must not pretend to validate a decoder stream.
    chunks.extend([chunk(b'IDAT', b'inert raw bytes'), chunk(b'IEND', b'')])
    details = dict(inspect_binary(wire(*chunks)).details)
    assert (details['color_type'], details['bit_depth'], details['interlace']) == (color, depth, interlace)
    assert not details['image_data_assessed']


@pytest.mark.parametrize('chunks', [
    [chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(), header(), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(), chunk(b'IEND', b'')],
    [header(), chunk(b'IDAT', b'')],
    [header(), chunk(b'IDAT', b''), chunk(b'tEXt', b'Own'), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(), chunk(b'IDAT', b''), chunk(b'PLTE', b'\x00\x01\x02'), chunk(b'IEND', b'')],
    [header(color=3), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(color=0), chunk(b'PLTE', b'\x00\x01\x02'), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(), chunk(b'PLTE', b'bad size'), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(color=3, depth=1), chunk(b'PLTE', b'\x00\x01\x02' * 3), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(), chunk(b'PLTE', b'\x00\x01\x02'), chunk(b'PLTE', b'\x00\x01\x02'), chunk(b'IDAT', b''), chunk(b'IEND', b'')],
    [header(), chunk(b'IDAT', b''), chunk(b'IEND', b'bad')],
])
def test_invalid_known_critical_order_and_palette_never_get_partial_inventory(chunks):
    with pytest.raises(InvalidDocumentError, match='png:'):
        inspect_binary(wire(*chunks), capture=True)


@pytest.mark.parametrize('values', [{'width': 0}, {'height': 0}, {'width': 0x80000000},
                                   {'color': 1}, {'depth': 4, 'color': 2}, {'depth': 16, 'color': 3}])
def test_invalid_header_fields_refuse(values):
    with pytest.raises(InvalidDocumentError, match='dimensions|depth/color'):
        inspect_binary(wire(header(**values), chunk(b'IDAT', b''), chunk(b'IEND', b'')))


@pytest.mark.parametrize('values', [{'compression': 1}, {'filtering': 1}, {'interlace': 2}])
def test_future_encoding_fields_are_explicitly_unsupported(values):
    with pytest.raises(UnsupportedDocumentError, match='compression/filter/interlace'):
        inspect_binary(wire(header(**values), chunk(b'IDAT', b''), chunk(b'IEND', b'')))


@pytest.mark.parametrize('source', [b'bad', own_png()[:-1], own_png() + b'junk',
                                   wire(struct.pack('>I', 0xffffffff) + b'IDAT' + b'\x00' * 4),
                                   wire(header(), chunk(b'a1Bc', b''), chunk(b'IDAT', b''), chunk(b'IEND', b''))])
def test_wire_boundary_length_and_type_fail_without_repair(source):
    with pytest.raises(InvalidDocumentError, match='png:'):
        inspect_binary(source, container='png')


def test_crc_mutation_is_detected_and_original_remains_readable():
    source = own_png()
    changed = bytearray(source)
    changed[45] ^= 1
    with pytest.raises(InvalidDocumentError, match='CRC mismatch'):
        inspect_binary(bytes(changed))
    assert inspect_binary(source).items


def test_unknown_chunks_and_animation_payloads_are_retained_without_semantic_claims():
    source = wire(header(), chunk(b'acTL', b'Own inert animation header'), chunk(b'ABCD', b'Unknown critical'),
                  chunk(b'vpAg', b'Own private bytes'), chunk(b'IDAT', b''), chunk(b'IEND', b''))
    snapshot = inspect_binary(source, capture=True)
    details = dict(snapshot.details)
    assert details['unknown_critical_chunks'] == ('ABCD',)
    assert details['ancillary_chunks'] == ('acTL', 'vpAg')
    assert not details['ancillary_semantics_assessed'] and not details['assessment_complete']
    assert b''.join(item.payload for item in snapshot.items) == source
    assert dict(next(item for item in snapshot.items if dict(item.details).get('chunk_type') == 'vpAg').details)['safe_to_copy']


@pytest.mark.parametrize('quota', ['max_input_bytes', 'max_part_bytes', 'max_total_bytes', 'max_items'])
def test_exact_inventory_quotas_and_one_below(quota):
    source = own_png()
    snapshot = inspect_binary(source)
    exact = {'max_input_bytes': len(source), 'max_total_bytes': len(source),
             'max_part_bytes': max(item.size for item in snapshot.items), 'max_items': len(snapshot.items)}[quota]
    assert inspect_binary(source, limits=replace(AnatomyLimits(), **{quota: exact})) == snapshot
    with pytest.raises(ResourceLimitError):
        inspect_binary(source, limits=replace(AnatomyLimits(), **{quota: exact - 1}))


def test_nested_png_occurrences_share_budget_and_do_not_decode_idat(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'PIL', 'pymupdf', 'fitz', 'docx', 'pptx', 'lxml'}:
            raise AssertionError(f'PNG inventory imported {name}')
        return original(name, *args, **kwargs)
    def forbidden(*args, **kwargs):
        pytest.fail('Physical PNG inspection attempted decompression')

    monkeypatch.setattr(builtins, '__import__', guarded)
    monkeypatch.setattr(zlib, 'decompress', forbidden)
    source = zip_bytes([('ppt/media/first.png', own_png()), ('ppt/media/second.png', own_png())],
                       compression=0)
    tree = inspect_container_tree(source, capture=True)
    assert [entry.snapshot.container for entry in tree.occurrences] == ['zip', 'png', 'png']
    assert tree.occurrences[1].location != tree.occurrences[2].location
    assert inspect_container_tree(source).to_dict() == tree.to_dict()
    for quota, exact in [('max_items', tree.charged_items), ('max_total_bytes', tree.charged_bytes)]:
        assert inspect_container_tree(source, limits=replace(AnatomyLimits(), **{quota: exact})) == tree
        with pytest.raises(ResourceLimitError):
            inspect_container_tree(source, limits=replace(AnatomyLimits(), **{quota: exact - 1}))


def test_png_text_containing_pdf_marker_does_not_change_profile():
    source = wire(header(), chunk(b'tEXt', b'Own\x00%PDF-1.7'), chunk(b'IDAT', b''), chunk(b'IEND', b''))
    assert inspect_binary(source).container == 'png'


def test_crc_valid_idat_edit_is_a_literal_chunk_change_not_pixel_fidelity():
    before = wire(header(), chunk(b'IDAT', b'Own first'), chunk(b'IEND', b''))
    after = wire(header(), chunk(b'IDAT', b'Own other'), chunk(b'IEND', b''))
    comparison = compare_snapshots(inspect_binary(before), inspect_binary(after))
    assert comparison['content_changed'] == ['png:chunk=1:IDAT'] and not comparison['assessment_complete']


def test_late_crc_cancellation_preserves_input_and_recovers_scope(tmp_path, monkeypatch):
    import opendoc_formats.native.png as implementation
    source = own_png()
    path = tmp_path / 'own.png'
    path.write_bytes(source)
    event = Event()
    original = implementation.zlib.crc32
    def cancelled(*args):
        value = original(*args)
        event.set()
        return value

    with monkeypatch.context() as context:
        context.setattr(implementation.zlib, 'crc32', cancelled)
        with pytest.raises(OperationCancelledError):
            inspect_binary(path, cancelled=event.is_set)
    assert path.read_bytes() == source
    assert inspect_binary(source).items


def test_cli_writes_generated_chunk_names_and_exact_source(tmp_path, monkeypatch):
    path, output = tmp_path / 'own.png', tmp_path / 'inventory'
    source = own_png()
    path.write_bytes(source)
    monkeypatch.setattr(sys, 'argv', ['document_anatomy', str(path), '--output', str(output), '--compare', str(path)])
    main()
    report = json.loads((output / 'inventory.json').read_text(encoding='utf-8'))
    assert report['container'] == 'png' and report['comparison']['binary_identical']
    assert b''.join((output / item['payload_file']).read_bytes() for item in report['items']) == source
