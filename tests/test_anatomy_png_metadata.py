"""Finite PNG declarations retain raw values, explicit unknowns and every bad occurrence."""

import builtins
import io
import struct
import zlib
from dataclasses import replace
from threading import Event

import pytest

from opendoc_formats.anatomy import inspect_binary
from opendoc_formats.errors import OperationCancelledError
from tests.test_anatomy_png import chunk, header, wire


def inspect(*metadata, color=2, depth=8, palette=None):
    chunks = [header(color=color, depth=depth)]
    if palette is not None:
        chunks.append(chunk(b'PLTE', palette))
    chunks.extend(metadata)
    chunks.extend([chunk(b'IDAT', b'inert bytes'), chunk(b'IEND', b'')])
    source = wire(*chunks)
    snapshot = inspect_binary(source, capture=True)
    assert b''.join(item.payload for item in snapshot.items) == source
    assert not dict(snapshot.details)['color_interpretation_assessed']
    return snapshot, dict(snapshot.details)


@pytest.mark.parametrize('depth,raw,expected', [(1, 0xfffe, 0), (2, 0xfffe, 2), (4, 0xfffe, 14),
                                               (8, 0xfffe, 254), (16, 0x1234, 0x1234)])
def test_grayscale_transparency_preserves_raw_sample_and_required_depth_mask(depth, raw, expected):
    _, details = inspect(chunk(b'tRNS', struct.pack('>H', raw)), color=0, depth=depth)
    declaration, = details['metadata_declarations']
    assert declaration['chunk_type'] == 'tRNS' and not details['metadata_findings']
    assert declaration['values'] == {'sample_depth': depth, 'transparent_samples_raw': (raw,),
                                     'transparent_samples': (expected,)}


@pytest.mark.parametrize('depth,expected', [(8, (0x34, 0xcd, 0xff)), (16, (0x1234, 0xabcd, 0xffff))])
def test_truecolor_transparency_keeps_entire_16_bit_samples(depth, expected):
    _, details = inspect(chunk(b'tRNS', struct.pack('>HHH', 0x1234, 0xabcd, 0xffff)), depth=depth)
    values = details['metadata_declarations'][0]['values']
    assert values['transparent_samples_raw'] == (0x1234, 0xabcd, 0xffff)
    assert values['transparent_samples'] == expected


@pytest.mark.parametrize('alpha', [b'', b'\x00', b'\x00\x40'])
def test_palette_alpha_records_only_declared_entries_and_explicit_opaque_remainder(alpha):
    _, details = inspect(chunk(b'tRNS', alpha), color=3, depth=1, palette=b'\x00\x01\x02' * 2)
    assert details['metadata_declarations'][0]['values'] == {
        'palette_entries': 2, 'declared_alpha': tuple(alpha), 'implicit_alpha': 255}


@pytest.mark.parametrize('intent', [0, 1, 2, 3])
def test_color_and_physical_declarations_remain_exact_integers_without_color_precedence(intent):
    _, details = inspect(chunk(b'pHYs', struct.pack('>IIB', 3780, 2835, 1)),
                         chunk(b'sRGB', bytes([intent])), chunk(b'gAMA', struct.pack('>I', 45455)))
    declarations = details['metadata_declarations']
    assert [entry['chunk_type'] for entry in declarations] == ['pHYs', 'sRGB', 'gAMA']
    assert declarations[0]['values'] == {'pixels_per_unit_x': 3780, 'pixels_per_unit_y': 2835, 'unit_specifier': 1}
    assert declarations[1]['values'] == {'rendering_intent': intent}
    assert declarations[2]['values'] == {'gamma_times_100000': 45455}
    assert not details['metadata_findings'] and not details['ancillary_semantics_assessed']


def test_unknown_resolution_does_not_become_assumed_dpi_or_square_pixels():
    _, details = inspect(chunk(b'pHYs', struct.pack('>IIB', 0, 2, 0)))
    assert details['metadata_declarations'][0]['values'] == {
        'pixels_per_unit_x': 0, 'pixels_per_unit_y': 2, 'unit_specifier': 0}
    assert 'dpi' not in str(details['metadata_declarations'])


@pytest.mark.parametrize('metadata,color', [(chunk(b'tRNS', b'bad'), 2), (chunk(b'tRNS', b'\x00'), 6),
                                          (chunk(b'gAMA', b'bad'), 2), (chunk(b'gAMA', b'\x00' * 4), 2),
                                          (chunk(b'sRGB', b''), 2), (chunk(b'sRGB', b'\x04'), 2),
                                          (chunk(b'pHYs', b'bad'), 2),
                                          (chunk(b'pHYs', struct.pack('>IIB', 1, 1, 2)), 2)])
def test_unaccepted_fields_remain_exact_opaque_bytes_with_located_findings(metadata, color):
    snapshot, details = inspect(metadata, color=color)
    assert details['metadata_declarations'] == ()
    finding, = details['metadata_findings']
    assert finding['code'].startswith('png.metadata.')
    assert finding['location'] == snapshot.items[2].locator and finding['message']
    assert not details['assessment_complete']


@pytest.mark.parametrize('name,payload', [(b'tRNS', struct.pack('>HHH', 1, 2, 3)),
                                        (b'gAMA', struct.pack('>I', 45455)), (b'sRGB', b'\x01'),
                                        (b'pHYs', struct.pack('>IIB', 1, 1, 0))])
def test_duplicate_metadata_selects_neither_occurrence_and_reports_both(name, payload):
    _, details = inspect(chunk(name, payload), chunk(name, payload))
    assert not details['metadata_declarations']
    assert [finding['location'] for finding in details['metadata_findings']] == [
        'png:chunk=1:' + name.decode(), 'png:chunk=2:' + name.decode()]
    assert all(finding['code'] == 'png.metadata.duplicate' for finding in details['metadata_findings'])


@pytest.mark.parametrize('kind,payload', [(b'tRNS', struct.pack('>HHH', 1, 2, 3)),
                                       (b'gAMA', struct.pack('>I', 45455)), (b'sRGB', b'\x00'),
                                       (b'pHYs', struct.pack('>IIB', 1, 1, 1))])
def test_late_metadata_is_not_interpreted(kind, payload):
    source = wire(header(), chunk(b'IDAT', b''), chunk(kind, payload), chunk(b'IEND', b''))
    details = dict(inspect_binary(source).details)
    assert not details['metadata_declarations']
    assert details['metadata_findings'][0]['code'] == 'png.metadata.order'


@pytest.mark.parametrize('kind,payload', [(b'gAMA', struct.pack('>I', 45455)), (b'sRGB', b'\x00')])
def test_color_metadata_after_palette_is_located(kind, payload):
    _, details = inspect(chunk(kind, payload), palette=b'\x00\x01\x02')
    assert not details['metadata_declarations']
    assert details['metadata_findings'][0]['code'] == 'png.metadata.order'


def test_transparency_before_optional_palette_is_not_silently_reordered():
    source = wire(header(), chunk(b'tRNS', struct.pack('>HHH', 1, 2, 3)),
                  chunk(b'PLTE', b'\x00\x01\x02'), chunk(b'IDAT', b''), chunk(b'IEND', b''))
    details = dict(inspect_binary(source).details)
    assert not details['metadata_declarations']
    assert details['metadata_findings'][0]['code'] == 'png.metadata.order'


@pytest.mark.parametrize('mode,pixel,key', [('L', 77, 77), ('RGB', (1, 2, 3), (1, 2, 3)), ('I;16', 513, 513)])
def test_independent_pillow_color_key_originals_agree_with_source_declarations(mode, pixel, key):
    image_module = pytest.importorskip('PIL.Image')
    with image_module.new(mode, (2, 1), pixel) as image:
        output = io.BytesIO()
        image.save(output, format='PNG', transparency=key)
    source = output.getvalue()
    snapshot = inspect_binary(source, capture=True)
    assert b''.join(item.payload for item in snapshot.items) == source
    declaration = next(entry for entry in dict(snapshot.details)['metadata_declarations'] if entry['chunk_type'] == 'tRNS')
    expected = key if isinstance(key, tuple) else (key,)
    assert declaration['values']['transparent_samples'] == expected
    with image_module.open(io.BytesIO(source)) as decoded:
        assert decoded.info['transparency'] == key


def test_independent_palette_alpha_and_density_gamma_original():
    image_module = pytest.importorskip('PIL.Image')
    plugin = pytest.importorskip('PIL.PngImagePlugin')
    info = plugin.PngInfo()
    info.add(b'gAMA', struct.pack('>I', 45455))
    info.add(b'sRGB', b'\x01')
    with image_module.new('P', (2, 1)) as image:
        image.putpalette([255, 0, 0, 0, 255, 0])
        image.putdata([0, 1])
        output = io.BytesIO()
        image.save(output, format='PNG', transparency=b'\x00', dpi=(96, 72), bits=1, pnginfo=info)
    source = output.getvalue()
    snapshot = inspect_binary(source, capture=True)
    declarations = {entry['chunk_type']: entry['values'] for entry in dict(snapshot.details)['metadata_declarations']}
    assert declarations['tRNS'] == {'palette_entries': 2, 'declared_alpha': (0,), 'implicit_alpha': 255}
    assert declarations['gAMA'] == {'gamma_times_100000': 45455}
    assert declarations['sRGB'] == {'rendering_intent': 1}
    with image_module.open(io.BytesIO(source)) as decoded:
        rgba = decoded.convert('RGBA')
        assert [rgba.getpixel((x, 0))[3] for x in range(2)] == [0, 255]
        assert decoded.info['dpi'][0] == pytest.approx(declarations['pHYs']['pixels_per_unit_x'] * 0.0254)
        assert decoded.info['gamma'] == pytest.approx(declarations['gAMA']['gamma_times_100000'] / 100000)
    assert b''.join(item.payload for item in snapshot.items) == source


def test_metadata_never_imports_decoder_or_expands_compressed_profiles(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'PIL', 'pymupdf', 'fitz', 'docx', 'pptx'}:
            raise AssertionError(f'Unnecessary decoder: {name}')
        return original(name, *args, **kwargs)
    def forbidden(*args, **kwargs):
        pytest.fail('Compressed metadata was decoded')

    monkeypatch.setattr(builtins, '__import__', guarded)
    monkeypatch.setattr(zlib, 'decompress', forbidden)
    _, details = inspect(chunk(b'iCCP', b'Own\x00\x00opaque compressed profile'), chunk(b'sRGB', b'\x00'))
    assert len(details['metadata_declarations']) == 1 and not details['color_interpretation_assessed']


def test_cancellation_during_metadata_pass_restores_scope_and_source(tmp_path, monkeypatch):
    import opendoc_formats.native.png_metadata as metadata
    source = wire(header(), chunk(b'gAMA', struct.pack('>I', 45455)), chunk(b'IDAT', b''), chunk(b'IEND', b''))
    path = tmp_path / 'own.png'
    path.write_bytes(source)
    event = Event()
    original = metadata.checkpoint
    def stop():
        event.set()
        original()

    with monkeypatch.context() as context:
        context.setattr(metadata, 'checkpoint', stop)
        with pytest.raises(OperationCancelledError):
            inspect_binary(path, cancelled=event.is_set)
    assert path.read_bytes() == source
    assert inspect_binary(source).items


def test_inventory_dictionary_cannot_mutate_nested_source_observations_or_future_fields():
    snapshot, _ = inspect(chunk(b'gAMA', struct.pack('>I', 45455)))
    signature = replace(snapshot.items[0], details=(('future', {'values': [1]}),))
    snapshot = replace(snapshot, items=(signature, *snapshot.items[1:]))
    output = snapshot.to_dict()
    output['details']['metadata_declarations'][0]['values']['gamma_times_100000'] = 1
    output['items'][0]['details']['future']['values'].append(2)
    assert dict(snapshot.details)['metadata_declarations'][0]['values']['gamma_times_100000'] == 45455
    assert dict(snapshot.items[0].details)['future']['values'] == [1]
