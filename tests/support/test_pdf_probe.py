"""Small PDF operations must work with each single-parser profile."""

import hashlib
import re
from importlib import import_module
from pathlib import Path

import pytest

from opendoc_formats.readers.pdf import get_pdf_info
from opendoc_formats.support import pdf_probe
from opendoc_formats.support.io import validate_pdf


@pytest.fixture
def source(tmp_path):
    fitz = pytest.importorskip('pymupdf')
    path = tmp_path / 'own.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((20, 30), 'Own PDF')
        document.set_metadata({'title': 'Own title / Проверка', 'author': 'Own author', 'subject': 'Own subject β'})
        document.save(path)
    return path


def test_native_probe_reads_independent_skia_pdf(tmp_path, monkeypatch):
    fixture = Path(__file__).resolve().parents[1] / 'corpus/native/skia-info.pdf'
    source = tmp_path / fixture.name
    source.write_bytes(fixture.read_bytes())
    expected = {'title': 'OpenDoc Metadata — Café Ω', 'author': '', 'subject': ''}
    pypdf = pytest.importorskip('pypdf')
    with pypdf.PdfReader(source, strict=True) as reference:
        assert reference.metadata.title == expected['title']
        assert reference.metadata.producer.startswith('Skia/PDF')
        assert len(reference.pages) == 1

    def missing(name):
        raise ImportError(name)

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    assert get_pdf_info(str(source)) == expected
    assert pdf_probe.probe_pdf(source)[0] == 1
    assert source.read_bytes() == fixture.read_bytes()


@pytest.mark.parametrize('engine', ['pypdf', 'pymupdf', 'pdfplumber'])
def test_each_single_backend_preserves_metadata_and_source(source, monkeypatch, engine):
    before = source.read_bytes()
    calls = []

    def only(name):
        calls.append(name)
        if name != engine:
            raise ImportError('Excluded by own profile')
        return import_module(name)

    monkeypatch.setattr(pdf_probe, 'import_module', only)
    assert validate_pdf(source)
    assert not calls
    assert get_pdf_info(str(source)) == {'title': 'Own title / Проверка', 'author': 'Own author', 'subject': 'Own subject β'}
    assert calls.count(engine) == 1
    assert source.read_bytes() == before


@pytest.mark.parametrize('engine', ['pypdf', 'pymupdf', 'pdfplumber'])
def test_each_profile_rejects_invalid_and_locked_pdf(source, tmp_path, monkeypatch, engine):
    fitz = import_module('pymupdf')
    locked = tmp_path / 'locked.pdf'
    with fitz.open(source) as document:
        document.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='own-owner', user_pw='own-user')
    invalid = tmp_path / 'invalid.pdf'
    invalid.write_bytes(b'Own invalid source')

    def only(name):
        if name != engine:
            raise ImportError('Excluded by own profile')
        return import_module(name)

    monkeypatch.setattr(pdf_probe, 'import_module', only)
    for path in [locked, invalid, tmp_path / 'missing.pdf']:
        digest = hashlib.sha256(path.read_bytes()).digest() if path.exists() else None
        assert not validate_pdf(path)
        assert get_pdf_info(str(path)) == {'title': '', 'author': '', 'subject': ''}
        if digest:
            assert hashlib.sha256(path.read_bytes()).digest() == digest


def test_no_backend_reads_metadata_and_checks_page_tree(source, monkeypatch):
    def missing(name):
        raise ImportError('Excluded by own profile')

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    assert validate_pdf(source)
    assert pdf_probe.probe_pdf(source)[0] == 1
    assert get_pdf_info(str(source)) == {'title': 'Own title / Проверка', 'author': 'Own author', 'subject': 'Own subject β'}


@pytest.mark.parametrize('trailer,closing,duplicate,expected', [
    (b'/Info 1 0 R', b'endobj', b'', {'title': 'Own (title)A — Café', 'author': 'AB €−˘���Z', 'subject': 'β'}),
    (b'/Info 1 0 R', b'endobj', b' /Subject <FEFF03B2>',
     {'title': 'Own (title)A — Café', 'author': 'AB €−˘���Z', 'subject': 'β'}),
    (b'/Info 1 0 R', b'endobj', b' /Subject (Other) /Subject <FEFF03B2>',
     {'title': 'Own (title)A — Café', 'author': 'AB €−˘���Z', 'subject': ''}),
    (b'/Info 1 1 R', b'endobj', b'', {'title': '', 'author': '', 'subject': ''}),
    (b'/Info 1 0 R /Encrypt 2 0 R', b'endobj', b'', {'title': '', 'author': '', 'subject': ''}),
    (b'/Info 1 0 R', b'notendobj', b'', {'title': '', 'author': '', 'subject': ''}),
])
def test_native_info_uses_xref_and_decodes_literal_and_hex_fields(tmp_path, monkeypatch, trailer, closing, duplicate, expected):
    def missing(name):
        raise ImportError('Excluded by own profile')

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    path = tmp_path / 'native.pdf'
    header = b'%PDF-1.7\n'
    info = (b'1 0 obj\n<< /Title (Own \\(title\\)\\\r\n\\101 \\204 Caf\\351) '
            b'/Author <41 42 20 A0 8A 18 7F 9F AD 5A> /Subject <FEFF03B2>'+duplicate+b' >>\n'+closing+b'\n')
    startxref = len(header)+len(info)
    records = f'xref\n0 2\n0000000000 65535 f \n{len(header):010d} 00000 n \n'.encode()
    data = header+info+records+b'trailer\n<< /Size 2 '+trailer+f' >>\nstartxref\n{startxref}\n%%EOF\n'.encode()
    path.write_bytes(data)
    assert get_pdf_info(str(path)) == expected
    assert path.read_bytes() == data


@pytest.mark.parametrize('index,generation,author,extra', [
    (0, 0, b'<A0>', b''), (0, 1, b'<A0>', b''), (1, 0, b'<A0>', b''),
    (0, 0, b'8 0 R', b''), (0, 0, b'5 0 R', b''),
    (0, 0, b'<A0>', b'/Subject 9 0 R'), (0, 0, b'<A0>', b'/Subject (Conflicting)'),
    (0, 0, b'<A0>', b'/Other << /X 1 /X 2 >>'),
])
def test_native_info_checks_current_compressed_member_identity(tmp_path, monkeypatch, index, generation, author, extra):
    from opendoc_formats.native import pdf_metadata
    from tests.native.test_pdf_extends import xref
    from tests.native.test_pdf_object_streams import custom_stream_pdf
    from tests.native.test_pdf_xref_state import latest

    def missing(name):
        raise ImportError('Excluded by own profile')

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    calls = []
    inspect_source = pdf_metadata.inspect_pdf_source

    def inspect_once(*args, **kwargs):
        calls.append(True)
        return inspect_source(*args, **kwargs)

    monkeypatch.setattr(pdf_metadata, 'inspect_pdf_source', inspect_once)
    info = f'<< /Title (Own compressed) /Author 5 {generation} R /Subject 9 0 R '.encode()+extra+b' >>'
    source, _, _ = custom_stream_pdf(members=[info, b'9 0 R', b'<FEFF03B2>'], flate=True)
    updated, revision = xref(source+b'5 0 obj\n'+author+b'\nendobj\n', 10,
                             {5: (1, len(source), 0), 7: (2, 4, index)}, previous=latest(source))
    marker = b'/Info 100 0 R'
    data = updated[:revision]+updated[revision:].replace(marker, b'/Info 7 0 R'.ljust(len(marker)), 1)
    path = tmp_path / 'compressed.pdf'
    path.write_bytes(data)
    author_text = {b'<A0>': '€', b'8 0 R': 'β', b'5 0 R': ''}[author]
    subject = '' if extra == b'/Subject (Conflicting)' else 'β'
    expected = ({'title': 'Own compressed', 'author': author_text if generation == 0 else '', 'subject': subject}
                if index == 0 and not extra.startswith(b'/Other') else dict.fromkeys(('title', 'author', 'subject'), ''))
    assert get_pdf_info(str(path)) == expected
    assert len(calls) == 1
    if extra:
        from opendoc_formats.anatomy import inspect_binary
        from opendoc_formats.errors import InvalidDocumentError

        with pytest.raises(InvalidDocumentError, match='duplicate dictionary key'):
            inspect_binary(data, pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True)


def test_existing_parser_error_is_not_hidden_by_another_engine(tmp_path, monkeypatch):
    source = tmp_path / 'invalid.pdf'
    source.write_bytes(b'Own invalid source')
    calls = []

    def observed(name):
        calls.append(name)
        return import_module(name)

    monkeypatch.setattr(pdf_probe, 'import_module', observed)
    assert not validate_pdf(source)
    assert calls == ['pypdf']


def test_backend_fallback_keeps_readable_page_count_when_declared_count_is_wrong(source, monkeypatch):
    original = source.read_bytes()
    data, count = re.subn(rb'/Count 1\b', b'/Count 2', original)
    assert count == 1
    source.write_bytes(data)
    calls = []

    def observed(name):
        calls.append(name)
        return import_module(name)

    monkeypatch.setattr(pdf_probe, 'import_module', observed)
    assert pdf_probe.probe_pdf(source)[0] == 1
    assert calls == ['pypdf']
    assert source.read_bytes() == data


def test_legacy_text_reader_skips_uninstalled_alternatives(source, monkeypatch):
    from opendoc_formats.readers import pdf

    monkeypatch.setattr(pdf, 'missing_backends', lambda names: [] if names == ('pymupdf',) else list(names))

    def forbidden(path):
        pytest.fail('An excluded alternative should not be attempted')

    monkeypatch.setattr(pdf, '_with_pdfplumber', forbidden)
    monkeypatch.setattr(pdf, '_with_pypdf', forbidden)
    text = pdf.read_pdf(str(source))
    assert text.engine.startswith('pymupdf') and 'Own PDF' in text.plain


def test_metadata_keeps_legacy_best_effort_without_reading_page_tree(source, monkeypatch):
    data, count = re.subn(rb'/Pages(\s+\d+\s+\d+\s+R)', rb'/Other\1', source.read_bytes())
    assert count == 1
    source.write_bytes(data)

    def only(name):
        if name != 'pypdf':
            raise ImportError('Excluded by own profile')
        return import_module(name)

    monkeypatch.setattr(pdf_probe, 'import_module', only)
    assert not validate_pdf(source)
    assert get_pdf_info(str(source)) == {'title': 'Own title / Проверка', 'author': 'Own author', 'subject': 'Own subject β'}


@pytest.mark.parametrize('old,new', [
    (rb'/Count 1\b', b'/Count 2'),
    (rb'/Type/Page(?=[/>])', b'/Type/Note'),
    (rb'/Parent 2 0 R', b'/Parent 1 0 R'),
    (rb'/Kids\[4 0 R\]', b'/Kids[2 0 R]'),
])
def test_native_page_tree_rejects_inconsistent_nodes(source, monkeypatch, old, new):
    def missing(name):
        raise ImportError('Excluded by own profile')

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    data, count = re.subn(old, new, source.read_bytes())
    assert count == 1 and len(data) == source.stat().st_size
    source.write_bytes(data)
    assert not validate_pdf(source)


@pytest.mark.parametrize('index,declared,expected', [(0, b'2', 2), (1, b'2', None), (0, b'1', None)])
def test_native_page_tree_reads_only_current_compressed_members(tmp_path, monkeypatch, index, declared, expected):
    from opendoc_formats.native import pdf_metadata
    from tests.native.test_pdf_extends import xref
    from tests.native.test_pdf_object_streams import custom_stream_pdf
    from tests.native.test_pdf_xref_state import latest

    def missing(name):
        raise ImportError('Excluded by own profile')

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    parser = pdf_metadata.Parser

    def source_parser(data, *args, **kwargs):
        assert data.startswith(b'%PDF-'), 'Page-tree probe parsed an ObjStm member again'
        return parser(data, *args, **kwargs)

    monkeypatch.setattr(pdf_metadata, 'Parser', source_parser)
    original, _, _ = custom_stream_pdf(members=[
        b'<< /Type /Catalog /Pages 8 0 R >>',
        b'<< /Type /Pages /Kids 11 0 R /Count 12 0 R /MediaBox [0 0 300 400] >>',
        b'<< /Type /Page /Parent 8 0 R >>',
        b'<< /Type /Page /Parent 8 0 R >>',
        b'[9 0 R 10 0 R]',
        declared,
    ])
    source, offset = xref(original, 13, {7: (2, 4, index)}, previous=latest(original))
    source = source[:offset]+source[offset:].replace(b'/Root 1 0 R', b'/Root 7 0 R')
    path = tmp_path/'compressed-pages.pdf'
    path.write_bytes(source)
    if expected is None:
        assert not validate_pdf(path)
    else:
        assert pdf_probe.probe_pdf(path)[0] == expected
        assert expected == len(import_module('pypdf').PdfReader(path, strict=True).pages)
    assert path.read_bytes() == source
