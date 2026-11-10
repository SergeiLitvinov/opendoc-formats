"""Independent ObjStm parameter references, historical contexts and strict refusals."""

import builtins
import hashlib
import json
import zlib
from dataclasses import replace
from io import BytesIO
from threading import Event

import pytest

from opendoc_formats.anatomy import AnatomyLimits, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError, UnsupportedDocumentError


def own_pdf(*, indirect=('N', 'First', 'Length'), generation=0, bodies=None, entry_kind=1, header_generation=None,
            filter_parameters=b''):
    payload = b'8 0 << /Title (Own indirect parameters) >>'
    if filter_parameters:
        payload = zlib.compress(payload)
    values = {'N': 1, 'First': 4, 'Length': len(payload)}
    identifiers = {'N': 5, 'First': 6, 'Length': 7}
    parameters = b' '.join(b'/'+key.encode()+b' '+(
        f'{identifiers[key]} {generation} R'.encode() if key in indirect else str(value).encode())
        for key, value in values.items())
    data = bytearray(b'%PDF-1.7\n')
    locations = {}
    objects = [(1, b'<< /Type /Catalog /Pages 2 0 R >>'),
               (2, b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>'),
               (3, b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>'),
               (4, b'<< /Type /ObjStm '+parameters+filter_parameters+b' >>\nstream\n'+payload+b'\nendstream')]
    objects += [(identifiers[key], (bodies or {}).get(key, str(value).encode())) for key, value in values.items()]
    for number, body in objects:
        locations[number] = len(data)
        gen = generation if number in (5, 6, 7) else 0
        if header_generation is not None and number == 7:
            gen = header_generation
        data.extend(f'{number} {gen} obj\n'.encode()+body+b'\nendobj\n')
    xref = len(data)
    records = [(0, 0, 65535)]
    for number in range(1, 8):
        kind = entry_kind if number == 7 else 1
        target = 4 if kind == 2 else locations[number]
        gen = (0 if kind == 2 else generation) if number in (5, 6, 7) else 0
        records.append((kind, target, gen))
    records += [(2, 4, 0), (1, xref, 0)]
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+gen.to_bytes(2, 'big') for kind, target, gen in records)
    data.extend(b'9 0 obj\n<< /Type /XRef /Size 10 /Root 1 0 R /Info 8 0 R /W [1 4 2] /Length '
                +str(len(raw)).encode()+b' >>\nstream\n'+raw+b'\nendstream\nendobj\nstartxref\n'
                +str(xref).encode()+b'\n%%EOF\n')
    return bytes(data), locations, values


def inspect(data, **kwargs):
    return inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True, **kwargs)


@pytest.mark.parametrize('array', [False, True])
def test_indirect_filter_name_is_observed_and_rechecked_after_revision(array):
    value = b'[5 2 R]' if array else b'5 2 R'
    source, locations, _ = own_pdf(indirect=(), generation=2, bodies={'N': b'/Flate#44ecode'},
                                   filter_parameters=b' /Filter ' + value)
    snapshot = inspect(source, capture=True)
    container = next(item for item in snapshot.items if item.kind == 'pdf-object-stream')
    field = 'Filter[0]' if array else 'Filter'
    observation, = dict(container.details)['source_integer_observations'][field]
    assert observation['offset'] == locations[5] and observation['value'] == 'FlateDecode'
    member = next(item for item in snapshot.items if item.kind == 'pdf-compressed-object')
    assert member.payload == b'<< /Title (Own indirect parameters) >>'

    previous = int(source.rsplit(b'startxref', 1)[1].split()[0])
    scalar = b'5 2 obj\n/LZWDecode\nendobj\n'
    table = len(source) + len(scalar)
    revised = source + scalar + (
        f'xref\n5 1\n{len(source):010} 00002 n \ntrailer\n'
        f'<< /Size 10 /Root 1 0 R /Prev {previous} >>\nstartxref\n{table}\n%%EOF\n'
    ).encode()
    link, = dict(inspect(revised).details)['compressed_object_current_links']
    assert link['status'] == 'container-changed-from-decoded-parameters'
    assert link['current_parameters']['current_parameter_values'] == {field: 'LZWDecode'}
    assert 'member_locator' not in link


def test_indirect_filter_name_does_not_accept_a_string_body():
    source, _, _ = own_pdf(indirect=(), bodies={'N': b'(FlateDecode)'}, filter_parameters=b' /Filter 5 0 R')
    with pytest.raises(UnsupportedDocumentError, match='direct name'):
        inspect(source)


@pytest.mark.parametrize('syntax, body, field, value', [
    (b'5 2 R', b'<< /Predictor 1 >>', 'DecodeParms', {'Predictor': 1}),
    (b'5 2 R', b'[<< /Predictor 1 >>]', 'DecodeParms', [{'Predictor': 1}]),
    (b'[5 2 R]', b'<< /Predictor 1 >>', 'DecodeParms[0]', {'Predictor': 1}),
])
def test_indirect_decodeparms_structures_are_observed_and_rechecked(syntax, body, field, value):
    source, locations, _ = own_pdf(indirect=(), generation=2, bodies={'N': body},
                                   filter_parameters=b' /Filter /FlateDecode /DecodeParms ' + syntax)
    snapshot = inspect(source, capture=True)
    container = next(item for item in snapshot.items if item.kind == 'pdf-object-stream')
    observation, = dict(container.details)['source_integer_observations'][field]
    assert observation['offset'] == locations[5] and observation['value'] == value
    assert next(item for item in snapshot.items if item.kind == 'pdf-compressed-object').payload == (
        b'<< /Title (Own indirect parameters) >>'
    )
    json.dumps(snapshot.to_dict())

    previous = int(source.rsplit(b'startxref', 1)[1].split()[0])
    scalar = b'5 2 obj\n' + body.replace(b'1', b'2') + b'\nendobj\n'
    table = len(source) + len(scalar)
    revised = source + scalar + (
        f'xref\n5 1\n{len(source):010} 00002 n \ntrailer\n'
        f'<< /Size 10 /Root 1 0 R /Prev {previous} >>\nstartxref\n{table}\n%%EOF\n'
    ).encode()
    link, = dict(inspect(revised).details)['compressed_object_current_links']
    assert link['status'] == 'container-changed-from-decoded-parameters'
    assert link['current_parameters']['decoded_parameter_values'] == {field: value}
    assert 'member_locator' not in link


def test_indirect_decodeparms_does_not_follow_recursive_references():
    source, _, _ = own_pdf(indirect=(), bodies={'N': b'<< /Predictor 5 0 R >>'},
                           filter_parameters=b' /Filter /FlateDecode /DecodeParms 5 0 R')
    with pytest.raises(UnsupportedDocumentError, match='direct nonnegative integers/null'):
        inspect(source)


@pytest.mark.parametrize('array', [False, True])
def test_indirect_filter_integer_has_source_and_current_context_evidence(array):
    options = b'<< /Predictor 5 2 R >>'
    if array:
        options = b'[' + options + b']'
    source, locations, _ = own_pdf(indirect=(), generation=2,
                                   filter_parameters=b' /Filter /FlateDecode /DecodeParms ' + options)
    snapshot = inspect(source, capture=True)
    container = next(item for item in snapshot.items if item.kind == 'pdf-object-stream')
    details = dict(container.details)
    assert details['predictor'] == 1
    field = 'DecodeParms[0]/Predictor' if array else 'DecodeParms/Predictor'
    observation, = details['source_integer_observations'][field]
    assert (observation['offset'], observation['generation'], observation['value']) == (locations[5], 2, 1)
    member = next(item for item in snapshot.items if item.kind == 'pdf-compressed-object')
    assert member.payload == b'<< /Title (Own indirect parameters) >>'
    link, = dict(snapshot.details)['compressed_object_current_links']
    current = link['current_parameters']
    assert current['decoded_parameter_values'] == {field: 1}
    assert current['status'] == 'matched-decoded-parameters'

    previous = int(source.rsplit(b'startxref', 1)[1].split()[0])
    scalar = b'5 2 obj\n2\nendobj\n'
    table = len(source) + len(scalar)
    revised = source + scalar + (
        f'xref\n5 1\n{len(source):010} 00002 n \ntrailer\n'
        f'<< /Size 10 /Root 1 0 R /Prev {previous} >>\nstartxref\n{table}\n%%EOF\n'
    ).encode()
    link, = dict(inspect(revised).details)['compressed_object_current_links']
    assert link['status'] == 'container-changed-from-decoded-parameters'
    assert link['current_parameters']['current_parameter_values'] == {field: 2}
    assert 'member_locator' not in link


@pytest.mark.parametrize('fields', [('N',), ('First',), ('Length',), ('N', 'First', 'Length')])
@pytest.mark.parametrize('generation', [0, 2])
def test_source_integer_observations_have_exact_ranges_and_match_independent_reader(fields, generation):
    data, locations, values = own_pdf(indirect=fields, generation=generation)
    snapshot = inspect(data, capture=True)
    container = next(item for item in snapshot.items if item.kind == 'pdf-object-stream')
    info = dict(container.details)
    assert not info['ownership_proven'] and not info['active_resolution']
    assert set(info['source_integer_observations']) == set(fields)
    for field in fields:
        observation, = info['source_integer_observations'][field]
        assert observation['value'] == values[field]
        assert observation['generation'] == generation
        assert observation['offset'] == locations[observation['object']]
        assert observation['sha256'] == hashlib.sha256(data[observation['offset']:observation['end']]).hexdigest()
        assert observation['context_xref'] == observation['primary_xref'] == observation['selected_xref']
        assert observation['record_range']['space'] == 'decoded-xref'
        assert not observation['ownership_proven']
    member = next(item for item in snapshot.items if item.kind == 'pdf-compressed-object')
    assert member.payload == b'<< /Title (Own indirect parameters) >>'
    assert not dict(snapshot.details)['object_stream_reference_links_assessed']
    pypdf = pytest.importorskip('pypdf')
    reader = pypdf.PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) == 1 and reader.metadata.title == 'Own indirect parameters'


@pytest.mark.parametrize('body', [b'-1', b'true', b'null', b'42.0', b'(42)', b'[]', b'<<>>', b'7 0 R'])
def test_scalar_must_be_nonnegative_direct_integer_without_recursive_or_backend_repair(body):
    data, _, _ = own_pdf(bodies={'Length': body})
    with pytest.raises(UnsupportedDocumentError, match='nonnegative direct integer'):
        inspect(data)


@pytest.mark.parametrize('kind', [0, 2, 7])
def test_free_compressed_and_unknown_entries_do_not_select_a_lexical_scalar_body(kind):
    data, _, _ = own_pdf(entry_kind=kind)
    with pytest.raises((InvalidDocumentError, UnsupportedDocumentError)):
        inspect(data)


@pytest.mark.parametrize('body', [b'42 43', b'42 endobj junk', b'999999', b'0'])
def test_wrong_scalar_body_or_length_never_searches_for_a_convenient_endstream(body):
    data, _, _ = own_pdf(bodies={'Length': body})
    if body == b'42 endobj junk':
        # The scalar itself legitimately ends at the first endobj, but its value is a wrong Length.
        data = data.replace(b'42 endobj junk', b'0  endobj junk')
    with pytest.raises(InvalidDocumentError):
        inspect(data)


def test_reference_generation_and_header_generation_are_both_checked():
    data, _, _ = own_pdf(generation=2)
    data = data.replace(b'/Length 7 2 R', b'/Length 7 1 R')
    with pytest.raises(InvalidDocumentError, match='generation'):
        inspect(data)
    data, _, _ = own_pdf(generation=2, header_generation=1)
    with pytest.raises(InvalidDocumentError, match='header'):
        inspect(data)


def appended(data, locations, values, *, value=None, include_container=True, free=False):
    previous = int(data.rsplit(b'startxref', 1)[1].split()[0])
    scalar = len(data)
    if value is not None:
        data += b'7 0 obj\n'+str(value).encode()+b'\nendobj\n'
    offset = len(data)
    data += b'xref\n'
    if include_container:
        data += f'4 1\n{locations[4]:010} 00000 n \n'.encode()
    if value is not None or free:
        data += f'7 1\n{0 if free else scalar:010} {1 if free else 0:05} {"f" if free else "n"} \n'.encode()
    data += (f'trailer\n<< /Size 10 /Root 1 0 R /Info 8 0 R /Prev {previous} >>\n'
             f'startxref\n{offset}\n%%EOF\n').encode()
    return data, offset


def test_historical_candidate_does_not_borrow_a_latest_scalar_from_an_unrelated_xref_context():
    data, locations, values = own_pdf()
    data, _ = appended(data, locations, values, value=0, include_container=False)
    snapshot = inspect(data, capture=True)
    container = next(item for item in snapshot.items if item.kind == 'pdf-object-stream')
    length, = dict(container.details)['source_integer_observations']['Length']
    assert length['value'] == values['Length'] and length['offset'] == locations[7]
    # This is a physical historical observation, not current type-2 object resolution.
    assert not dict(snapshot.details)['object_stream_reference_links_assessed']


def test_repeated_candidate_contexts_must_agree_and_preserve_prev_lookup_provenance():
    data, locations, values = own_pdf()
    same, offset = appended(data, locations, values, value=values['Length'])
    container = next(item for item in inspect(same).items if item.kind == 'pdf-object-stream')
    observations = dict(container.details)['source_integer_observations']
    assert len(observations['Length']) == 2
    assert len({row['offset'] for row in observations['Length']}) == 2
    assert any(row['context_xref'] == offset and row['selected_xref'] != offset for row in observations['N'])
    different, _ = appended(data, locations, values, value=0)
    with pytest.raises(UnsupportedDocumentError, match='differs across'):
        inspect(different)
    freed, _ = appended(data, locations, values, free=True)
    with pytest.raises(InvalidDocumentError, match='no in-use'):
        inspect(freed)


@pytest.mark.parametrize('field,maximum', [('max_items', 25), ('max_total_bytes', 460), ('max_pdf_tokens', 85)])
def test_scalar_and_lookup_work_share_global_quotas(field, maximum):
    data, _, _ = own_pdf()
    with pytest.raises(ResourceLimitError):
        inspect(data, limits=replace(AnatomyLimits(), **{field: maximum}))


@pytest.mark.parametrize('field', ['max_items', 'max_total_bytes'])
def test_shared_quota_accepts_exact_total_and_refuses_one_less(field):
    data, _, _ = own_pdf()
    snapshot = inspect(data)
    details = dict(snapshot.details)
    xrefs = [item for item in snapshot.items if item.kind in {'pdf-classic-xref', 'pdf-xref-stream'}]
    if field == 'max_items':
        maximum = sum(1+len(dict(item.details)['entries']) for item in xrefs)
        maximum += sum(item.kind in {'pdf-object-stream', 'pdf-compressed-object'} for item in snapshot.items)
        maximum += details['source_integer_work_items']
        maximum += details['object_stream_link_work_items']
        maximum += details['object_stream_extends_work_items']
    else:
        maximum = sum(item.size for item in xrefs)+details['xref_decode_work_bytes']+details['object_stream_work_bytes']
    inspect(data, limits=replace(AnatomyLimits(), **{field: maximum}))
    with pytest.raises(ResourceLimitError):
        inspect(data, limits=replace(AnatomyLimits(), **{field: maximum-1}))


@pytest.mark.parametrize('limits,quota', [(AnatomyLimits(max_part_bytes=512), 'max_part_bytes'),
                                        (AnatomyLimits(max_total_bytes=900), 'max_total_bytes')])
def test_scalar_window_is_bounded_before_long_body_scan(limits, quota):
    data, _, values = own_pdf()
    data, _, _ = own_pdf(bodies={'Length': b' '*2000+str(values['Length']).encode()})
    with pytest.raises(ResourceLimitError, match=quota):
        inspect(data, limits=limits)


def test_cancel_during_indirect_lookup_has_no_backend_fallback(monkeypatch):
    from opendoc_formats.native import pdf_source_integers

    data, _, _ = own_pdf()
    original = bytes(data)
    stop = Event()
    real = pdf_source_integers.resolve_xrefs

    def selected(*args, **kwargs):
        result = real(*args, **kwargs)
        stop.set()
        return result

    monkeypatch.setattr(pdf_source_integers, 'resolve_xrefs', selected)
    with pytest.raises(OperationCancelledError):
        inspect(data, cancelled=stop.is_set)
    assert data == original


@pytest.mark.parametrize('dual_role', [False, True])
def test_hybrid_candidate_uses_its_primary_table_before_supplement_prev(dual_role):
    data, locations, values = own_pdf()
    previous = int(data.rsplit(b'startxref', 1)[1].split()[0])
    scalar = len(data)
    data += b'7 0 obj\n'+str(values['Length']).encode()+b'\nendobj\n'
    supplement = len(data)
    raw = b'\x01'+locations[4].to_bytes(4, 'big')+b'\0\0'
    data += (b'10 0 obj\n<< /Type /XRef /Size 11 /W [1 4 2] /Index [4 1] /Length 7 '
             +f'/Prev {previous} >>\nstream\n'.encode()+raw+b'\nendstream\nendobj\n')
    primary = len(data)
    data += (f'xref\n7 1\n{scalar:010} 00000 n \ntrailer\n<< /Size 11 /Root 1 0 R '
             f'/Prev {supplement if dual_role else previous} /XRefStm {supplement} >>\n'
             f'startxref\n{primary}\n%%EOF\n').encode()
    if dual_role:
        with pytest.raises(UnsupportedDocumentError, match='ambiguous hybrid primary'):
            inspect(data)
        return
    container = next(item for item in inspect(data).items if item.kind == 'pdf-object-stream')
    lengths = dict(container.details)['source_integer_observations']['Length']
    observation = next(row for row in lengths if row['context_xref'] == supplement)
    assert observation['primary_xref'] == observation['selected_xref'] == primary
    assert observation['offset'] == scalar


def test_non_object_stream_reuse_keeps_indirect_length_and_never_decodes_ordinary_payload():
    data, _, _ = own_pdf()
    previous = int(data.rsplit(b'startxref', 1)[1].split()[0])
    payload = b'own stream endstream endobj bytes'
    candidate = len(data)
    data += (b'4 2 obj\n<< /Type /XObject /Length 7 0 R /Filter /NeverExecute >>\nstream\n'
             +payload+b'\nendstream\nendobj\n')
    scalar = len(data)
    data += b'7 0 obj\n'+str(len(payload)).encode()+b'\nendobj\n'
    offset = len(data)
    data += (f'xref\n4 1\n{candidate:010} 00002 n \n7 1\n{scalar:010} 00000 n \ntrailer\n'
             f'<< /Size 10 /Root 1 0 R /Prev {previous} >>\nstartxref\n{offset}\n%%EOF\n').encode()
    snapshot = inspect(data, capture=True)
    item, = [item for item in snapshot.items if item.kind == 'pdf-non-object-stream-candidate']
    info = dict(item.details)
    assert info['generation'] == 2 and not info['ownership_proven']
    assert data[info['encoded_start']:info['encoded_end']] == payload
    assert info['source_integer_observations']['Length'][0]['offset'] == scalar
    assert item.payload == data[candidate:info['end']]
    assert dict(snapshot.details)['decoded_object_streams'] == 1


def test_scalar_profile_uses_no_pdf_or_image_backend(monkeypatch):
    data, _, _ = own_pdf()
    native_import = builtins.__import__

    def minimal(name, *args, **kwargs):
        if name.split('.')[0] in {'pypdf', 'fitz', 'pymupdf', 'PIL', 'pdfplumber', 'numpy', 'lxml'}:
            raise AssertionError('Unexpected backend: '+name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', minimal)
    assert dict(inspect(data).details)['decoded_object_streams'] == 1


def test_cli_preserves_scalar_evidence_and_previous_destination_on_late_refusal(tmp_path, monkeypatch):
    from tools.document_anatomy import main

    source, output = tmp_path/'own.pdf', tmp_path/'dissected'
    data, _, _ = own_pdf()
    source.write_bytes(data)
    monkeypatch.setattr('sys.argv', ['document_anatomy', str(source), '--pdf-source', '--pdf-decode-xrefs',
                                    '--pdf-object-streams', '--output', str(output)])
    main()
    inventory = json.loads((output/'inventory.json').read_text(encoding='utf-8'))
    container = next(item for item in inventory['items'] if item['kind'] == 'pdf-object-stream')
    assert set(container['details']['source_integer_observations']) == {'N', 'First', 'Length'}
    assert source.read_bytes() == data
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    damaged, _, _ = own_pdf(bodies={'Length': b'-1'})
    source.write_bytes(damaged)
    with pytest.raises(UnsupportedDocumentError):
        main()
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert source.read_bytes() == damaged
