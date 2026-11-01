"""Historical ObjStm numbers reused by ordinary objects; independent incremental PDFs."""

import hashlib
from dataclasses import replace
from io import BytesIO

import pytest

from opendoc_formats.anatomy import AnatomyLimits
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError
from tests.native.test_pdf_object_streams import custom_stream_pdf, inspect

BODIES = [b'<< /Type /Example /Value (new) >>', b'(ordinary string)', b'42', b'null', b'[1 /Name (new)]',
          b'<< /Length 23 /Filter /UnknownCodec >>\nstream\nembedded endobj\x00stream\n\nendstream']


def reused_pdf(body, generation=1):
    original, _, locations = custom_stream_pdf(flate=False)
    previous = int(original.rsplit(b'startxref', 1)[1].split()[0])
    # Free the old container and all its members in one revision.
    freed_xref = len(original)
    data = original+(f'xref\n4 1\n0000000000 {generation:05} f \n7 4\n'.encode()
                     +b'0000000000 00001 f \n'*4
                     +f'trailer\n<< /Size 11 /Root 1 0 R /Info null /Prev {previous} >>\n'
                      f'startxref\n{freed_xref}\n%%EOF\n'.encode())
    offset = len(data)
    data += f'4 {generation} obj\n'.encode()+body+b'\nendobj\n'
    xref = len(data)
    data += (f'xref\n4 1\n{offset:010} {generation:05} n \ntrailer\n'
             f'<< /Size 11 /Root 1 0 R /Info null /Prev {freed_xref} >>\n'
             f'startxref\n{xref}\n%%EOF\n').encode()
    return data, offset, locations[4]


@pytest.mark.parametrize('body', BODIES, ids=['dictionary', 'string', 'integer', 'null', 'array', 'stream'])
@pytest.mark.parametrize('generation', [1, 5, 65535])
def test_reuse_preserves_old_container_and_new_ordinary_object(body, generation):
    data, offset, old = reused_pdf(body, generation)
    snapshot = inspect(data, capture=True, pdf_resolve_xrefs=True)
    candidates = [item for item in snapshot.items if item.kind == 'pdf-non-object-stream-candidate']
    assert len(candidates) == 1
    item = candidates[0]
    info = dict(item.details)
    assert info['offset'] == offset and info['generation'] == generation
    assert info['candidate_status'] == 'not-object-stream' and not info['active_resolution']
    assert not info['ownership_proven']
    assert item.payload == data[offset:info['end']] == f'4 {generation} obj\n'.encode()+body+b'\nendobj'
    assert item.sha256 == hashlib.sha256(item.payload).hexdigest()
    old_items = [item for item in snapshot.items if item.kind == 'pdf-object-stream']
    assert len(old_items) == 1 and dict(old_items[0].details)['offset'] == old
    report = dict(snapshot.details)
    assert report['decoded_object_streams'] == report['non_object_stream_candidates'] == 1
    assert not report['object_stream_reference_links_assessed'] and not report['object_resolution_complete']
    selected = next(row for row in report['effective_xref_entries'] if row['object'] == 4)
    assert selected['generation'] == generation and selected['offset'] == offset
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1
    value = reader.get_object(pypdf.generic.IndirectObject(4, generation, reader))
    if body.startswith(b'<< /Length'):
        assert value._data == b'embedded endobj\x00stream\n'
    mupdf = pytest.importorskip('pymupdf')
    with mupdf.open(stream=data, filetype='pdf') as reader:
        assert not reader.is_repaired and len(reader) == 1
        if body.startswith(b'<< /Length'):
            assert reader.xref_stream_raw(4) == b'embedded endobj\x00stream\n'
    assert all(item.payload is None for item in inspect(data).items)


@pytest.mark.parametrize('damage', ['header', 'closing', 'length', 'indirect', 'extra', 'line-ending'])
def test_bad_candidate_refuses_without_searching_for_delimiters(damage):
    body = BODIES[-1]
    if damage == 'length':
        body = body.replace(b'/Length 23', b'/Length 999999')
    elif damage == 'indirect':
        body = body.replace(b'/Length 23', b'/Length 99 0 R')
    elif damage == 'extra':
        body = b'42 43'
    elif damage == 'line-ending':
        body = body.replace(b'stream\nembedded', b'stream embedded')
    data, offset, _ = reused_pdf(body)
    if damage == 'header':
        data = data[:offset]+data[offset:].replace(b'4 1 obj', b'4 2 obj', 1)
    elif damage == 'closing':
        data = data[:offset]+data[offset:].replace(b'endstream', b'endstrxxx', 1)
    expected = UnsupportedDocumentError if damage == 'indirect' else InvalidDocumentError
    with pytest.raises(expected, match='pdf:source-objstm'):
        inspect(data)


@pytest.mark.parametrize('field', ['max_items', 'max_total_bytes'])
def test_candidate_counts_toward_shared_exact_budget(field):
    data, _, _ = reused_pdf(BODIES[0])
    snapshot = inspect(data)
    report = dict(snapshot.details)
    # PDF physical sections, decoded xrefs, containers and selected records share quotas.
    maximum = (sum(1+len(dict(item.details).get('entries', [])) for item in snapshot.items
                   if item.kind in {'pdf-classic-xref', 'pdf-xref-stream'})
               +sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object', 'pdf-non-object-stream-candidate'}
                    for item in snapshot.items)) if field == 'max_items' else (
                        sum(item.size for item in snapshot.items if item.kind in {'pdf-classic-xref', 'pdf-xref-stream'})
                        +report['xref_decode_work_bytes']+report['object_stream_work_bytes'])
    inspect(data, limits=replace(AnatomyLimits(), **{field: maximum}))
    with pytest.raises(ResourceLimitError):
        inspect(data, limits=replace(AnatomyLimits(), **{field: maximum-1}))


def test_cancel_during_ordinary_candidate(monkeypatch):
    from opendoc_formats.native import pdf_object_streams
    data, _, _ = reused_pdf(BODIES[0])
    stopped = False
    real = pdf_object_streams._candidate_end
    def cancel(*args, **kwargs):
        nonlocal stopped
        stopped = True
        return real(*args, **kwargs)
    monkeypatch.setattr(pdf_object_streams, '_candidate_end', cancel)
    with pytest.raises(OperationCancelledError):
        inspect(data, cancelled=lambda: stopped)



def test_cli_ordinary_candidate_payload_and_late_refusal_are_atomic(tmp_path, monkeypatch):
    import json

    from tools.document_anatomy import main
    good, offset, _ = reused_pdf(BODIES[-1])
    source, output = tmp_path/'source.pdf', tmp_path/'inventory'
    source.write_bytes(good)
    monkeypatch.setattr('sys.argv', ['anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs',
                                   '--pdf-object-streams', '--output', str(output)])
    main()
    before = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
    inventory = json.loads(before['inventory.json'])
    item = next(row for row in inventory['items'] if row['kind'] == 'pdf-non-object-stream-candidate')
    assert (output/item['payload_file']).read_bytes() == good[offset:item['details']['end']]
    bad = good[:offset]+good[offset:].replace(b'endstream', b'endstrxxx', 1)
    source.write_bytes(bad)
    with pytest.raises(InvalidDocumentError):
        main()
    assert source.read_bytes() == bad
    assert before == {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}
