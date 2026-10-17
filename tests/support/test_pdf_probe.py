"""Small PDF operations must work with each single-parser profile."""

import hashlib
import re
from importlib import import_module

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
    assert get_pdf_info(str(source)) == {'title': 'Own title / Проверка', 'author': 'Own author', 'subject': 'Own subject β'}
    assert calls.count(engine) == 2
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


def test_no_backend_keeps_legacy_failure_result(source, monkeypatch):
    def missing(name):
        raise ImportError('Excluded by own profile')

    monkeypatch.setattr(pdf_probe, 'import_module', missing)
    assert not validate_pdf(source)
    assert get_pdf_info(str(source)) == {'title': '', 'author': '', 'subject': ''}


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
