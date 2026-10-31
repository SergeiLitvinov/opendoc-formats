"""Own physical incremental xrefs establish source truth without a repair backend."""

import json
from dataclasses import replace
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, compare_snapshots, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from tests.binary_fixtures import own_pdf


def latest(data):
    return int(data.rsplit(b'startxref', 1)[1].split()[0])


def append_update(data, *, generation=2, extra=b'', previous=None):
    previous = latest(data) if previous is None else previous
    target = len(data)
    data += f'4 {generation} obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n'.encode()
    offset = len(data)
    data += (f'xref\n4 1\n{target:010} {generation:05} n \ntrailer\n'
             f'<< /Size 7 /Root 1 0 R /Prev {previous} '.encode()+extra+b'>>\n'
             +f'startxref\n{offset}\n%%EOF\n'.encode())
    return data


def test_classic_source_sections_generations_original_bytes_and_literal_comparison():
    original, _ = own_pdf()
    result = append_update(original)
    snapshot = inspect_binary(result, pdf_source=True, capture=True)
    details = dict(snapshot.details)
    assert snapshot.container == 'pdf' and not details['backend_used'] and details['xref_sections'] == 2
    assert not details['assessment_complete'] and not details['object_streams_decoded']
    newest, oldest = snapshot.items
    entries = dict(newest.details)['entries']
    assert entries == [{'object': 4, 'generation': 2, 'offset_or_next_free': len(original), 'in_use': True,
                        'entry_start': entries[0]['entry_start'], 'entry_end': entries[0]['entry_end'],
                        'object_header_matches': True}]
    for item in snapshot.items:
        info = dict(item.details)
        assert item.payload == result[info['offset']:info['end']]
    assert all(e['object_header_matches'] for e in dict(oldest.details)['entries'] if e['in_use'])
    difference = compare_snapshots(inspect_binary(original, pdf_source=True), snapshot)
    assert difference['added'] == [newest.locator]
    assert not difference['content_changed'] and not difference['removed']
    json.dumps(snapshot.to_dict())


def test_nested_strings_comments_hex_and_escaped_prev_names_do_not_confuse_trailer():
    original, _ = own_pdf()
    result = append_update(original, extra=b'/Info << /Text (fake /Prev 123 (nested \\) text)) /Hex <2f50726576> >> '
                           b'/Array [1 0 R null true false 1.25 /Name#20Space] % /Prev 9999\n')
    result = result.replace(b'/Prev '+str(latest(original)).encode(), b'/Pr#65v '+str(latest(original)).encode())
    snapshot = inspect_binary(result, pdf_source=True)
    assert dict(snapshot.details)['xref_sections'] == 2
    assert dict(snapshot.items[0].details)['prev'] == latest(original)


@pytest.mark.parametrize('newline', [b'\n', b'\r\n', b'\r'])
def test_source_tokenization_accepts_pdf_line_endings(newline):
    data = b'%PDF-1.7\n1 0 obj\nnull\nendobj\n'
    offset = len(data)
    data += (b'xref\n0 2\n0000000000 65535 f \n0000000001 00000 n \ntrailer\n'
             b'<< /Size 2 /Root 1 0 R >>\nstartxref\n'+str(offset).encode()+b'\n%%EOF\n')
    # Only footer/index line endings change; entry target remains deliberately
    # reported as unmatched, rather than being silently repaired.
    data = data[:offset]+data[offset:].replace(b'\n', newline)
    snapshot = inspect_binary(data, pdf_source=True)
    assert dict(snapshot.details)['xref_sections'] == 1
    assert dict(snapshot.items[0].details)['entries'][1]['object_header_matches'] is False


def stream_pdf(*, previous=None, supplement=None):
    data = b'%PDF-1.7\n'
    offset = len(data)
    dictionary = b'<< /Type /XRef /Size 2 /W [1 2 1] /Length 4 '
    if previous is not None:
        dictionary += b'/Prev '+str(previous).encode()+b' '
    dictionary += b'>>'
    data += b'1 0 obj\n'+dictionary+b'\nstream\n\x01\x00\x09\x00\nendstream\nendobj\n'
    if supplement:
        table = len(data)
        data += b'xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 2 /XRefStm '+str(offset).encode()+b' >>\n'
        offset = table
    data += b'startxref\n'+str(offset).encode()+b'\n%%EOF\n'
    return data


@pytest.mark.parametrize('hybrid', [False, True])
def test_xref_stream_and_hybrid_dictionary_are_explicit_opaque_without_stream_decoder(hybrid):
    data = stream_pdf(supplement=hybrid)
    snapshot = inspect_binary(data, pdf_source=True, capture=True)
    assert dict(snapshot.details)['has_xref_streams']
    stream = next(item for item in snapshot.items if item.kind == 'pdf-xref-stream-dictionary')
    assert dict(stream.details)['stream_entries_decoded'] is False
    assert stream.payload.endswith(b'>>') and b'endstream' not in stream.payload
    assert dict(stream.details)['hybrid_supplement'] is hybrid


@pytest.mark.parametrize('damage', ['cycle', 'outside', 'duplicate', 'indirect', 'bad-start', 'junk', 'overlap'])
def test_unproved_links_and_ambiguous_dictionaries_refuse_without_repair(damage):
    data, _ = own_pdf()
    if damage == 'cycle':
        data = append_update(data, previous=latest(data))
        offset = latest(data)
        data = data[:offset]+data[offset:].replace(b'/Prev '+str(latest(own_pdf()[0])).encode(), b'/Prev '+str(offset).encode())
    elif damage == 'outside':
        data = append_update(data, previous=99999999)
    elif damage == 'duplicate':
        data = append_update(data, extra=b'/Pr#65v 0 ')
    elif damage == 'indirect':
        data = append_update(data).replace(b'/Prev '+str(latest(data)).encode(), b'/Prev 1 0 R')
    elif damage == 'bad-start':
        data = data.replace(b'startxref\n'+str(latest(data)).encode(), b'startxref\n0')
    elif damage == 'junk':
        data += b'own trailing garbage'
    else:
        offset = latest(data)
        data = data[:offset]+data[offset:].replace(b'trailer', b'0 1\n0000000000 65535 f \ntrailer', 1)
    with pytest.raises(InvalidDocumentError):
        inspect_binary(data, pdf_source=True)


@pytest.mark.parametrize('quota,maximum', [('max_items', 2), ('max_part_bytes', 40), ('max_total_bytes', 40),
                                           ('max_pdf_tokens', 5), ('max_pdf_depth', 1)])
def test_selected_source_budgets_are_honored(quota, maximum):
    data, _ = own_pdf()
    data = append_update(data, extra=b'/Nested [[[[1]]]] ')
    with pytest.raises(ResourceLimitError):
        inspect_binary(data, pdf_source=True, limits=replace(AnatomyLimits(), **{quota: maximum}))


def test_source_cancellation_stops_before_later_sections_and_preserves_input(monkeypatch):
    from opendoc_formats.native import pdf_revisions

    data = append_update(own_pdf()[0])
    original = bytes(data)
    stop = Event()
    count = 0
    real = pdf_revisions.checkpoint
    def checkpoint():
        nonlocal count
        count += 1
        if count == 3:
            stop.set()
        real()
    monkeypatch.setattr(pdf_revisions, 'checkpoint', checkpoint)
    with pytest.raises(OperationCancelledError):
        inspect_binary(data, pdf_source=True, cancelled=stop.is_set)
    assert data == original and count == 3


def test_classic_wire_offsets_agree_with_independent_reader_on_valid_incremental_pdf():
    pypdf = pytest.importorskip('pypdf')
    from io import BytesIO

    original, _ = own_pdf()
    target = len(original)
    updated = original+b'7 0 obj\n<< /Title (Own source history) >>\nendobj\n'
    xref = len(updated)
    updated += (f'xref\n7 1\n{target:010} 00000 n \ntrailer\n'
                f'<< /Size 8 /Root 1 0 R /Info 7 0 R /Prev {latest(original)} >>\n'
                f'startxref\n{xref}\n%%EOF\n').encode()
    native = pypdf.PdfReader(BytesIO(updated), strict=True)
    assert len(native.pages) == 1 and native.metadata.title == 'Own source history'
    snapshot = inspect_binary(updated, pdf_source=True)
    for section in snapshot.items:
        for entry in dict(section.details)['entries']:
            if entry['in_use']:
                assert native.xref[entry['generation']][entry['object']] == entry['offset_or_next_free']


def test_pdf_source_flag_rejects_other_containers_and_nonboolean_values():
    with pytest.raises(ValueError, match='requires the pdf'):
        inspect_binary(b'not a zip', container='zip', pdf_source=True)
    with pytest.raises(TypeError):
        inspect_binary(own_pdf()[0], pdf_source=1)
