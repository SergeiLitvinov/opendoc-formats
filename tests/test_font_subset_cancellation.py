"""Cancellation at engine boundaries must never masquerade as full-font fallback."""

import builtins
from threading import Event

import pytest
from fontTools import subset
from fontTools.ttLib import TTFont

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts.embedding import FontUsage, subset_font
from opendoc_formats.support.cancellation import cancellation_scope
from tests.binary_fixtures import own_placement_font


def usage_at(tmp_path, *, characters='AB', subsettable=True):
    path = tmp_path/'own.ttf'
    path.write_bytes(own_placement_font())
    return FontUsage('Own', path, False, False, frozenset(characters), True, subsettable)


@pytest.mark.parametrize('stage', ['populate', 'subset', 'save', 'close'])
@pytest.mark.parametrize('engine_error', [False, True])
def test_cancellation_after_engine_stage_closes_font_without_fallback(tmp_path, monkeypatch, stage, engine_error):
    usage = usage_at(tmp_path)
    before = usage.path.read_bytes()
    stop, calls = Event(), []
    owner = subset.Subsetter if stage in ('populate', 'subset') else TTFont
    original = getattr(owner, stage)
    original_close = TTFont.close

    def close(self):
        calls.append('close')
        return original_close(self)

    monkeypatch.setattr(TTFont, 'close', close)

    def interrupted(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        stop.set()
        if engine_error:
            raise RuntimeError('Own backend failure with cancellation pending')
        return result

    if stage == 'close':
        def interrupted_close(self):
            close(self)
            stop.set()
            if engine_error:
                raise RuntimeError('Own close failure with cancellation pending')
        monkeypatch.setattr(TTFont, 'close', interrupted_close)
    else:
        monkeypatch.setattr(owner, stage, interrupted)
    with cancellation_scope(stop.is_set, 'Subset own font'):
        with pytest.raises(OperationCancelledError):
            subset_font(usage)
        stop.clear()
    assert calls == ['close']
    assert usage.path.read_bytes() == before


def test_engine_raised_cancellation_is_not_swallowed(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    calls = []
    original = TTFont.close

    def cancelled(self, *args, **kwargs):
        raise OperationCancelledError('Own engine cancellation')

    def close(self):
        calls.append(True)
        return original(self)

    monkeypatch.setattr(subset.Subsetter, 'subset', cancelled)
    monkeypatch.setattr(TTFont, 'close', close)
    with pytest.raises(OperationCancelledError, match='Own engine'):
        subset_font(usage)
    assert calls == [True]


def test_non_cancelled_engine_failure_preserves_full_font_and_closes_handle(tmp_path, monkeypatch):
    usage = usage_at(tmp_path)
    before, calls = usage.path.read_bytes(), []
    original = TTFont.close

    def unsupported(self, *args, **kwargs):
        raise ValueError('Own unsupported program')

    def close(self):
        calls.append(True)
        return original(self)

    monkeypatch.setattr(subset.Subsetter, 'subset', unsupported)
    monkeypatch.setattr(TTFont, 'close', close)
    assert subset_font(usage) == before == usage.path.read_bytes()
    assert calls == [True]


@pytest.mark.parametrize('characters,subsettable', [('', True), ('AB', False)])
def test_full_font_paths_require_no_engine(tmp_path, monkeypatch, characters, subsettable):
    usage = usage_at(tmp_path, characters=characters, subsettable=subsettable)
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name == 'fontTools' or name.startswith('fontTools.'):
            pytest.fail('Full font path imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert subset_font(usage) == usage.path.read_bytes()


def test_pending_cancellation_prevents_source_read(tmp_path, monkeypatch):
    import opendoc_formats.fonts.embedding as native

    usage = usage_at(tmp_path)
    stop = Event()

    def checkpoint():
        stop.set()
        from opendoc_formats.support.cancellation import checkpoint as check
        check()

    monkeypatch.setattr(native, 'checkpoint', checkpoint)

    def forbidden(self):
        pytest.fail('Cancelled subset read source bytes')

    monkeypatch.setattr(type(usage.path), 'read_bytes', forbidden)
    with cancellation_scope(stop.is_set, 'Own subset'):
        with pytest.raises(OperationCancelledError):
            subset_font(usage)
        stop.clear()


@pytest.mark.parametrize('public', [False, True])
def test_docx_cancelled_during_real_subsetting_keeps_model_source_and_destination(tmp_path, monkeypatch, public):
    from opendoc_model import DocumentModel, Paragraph, Section, TextRun, TextStyle, document_to_json

    from opendoc_formats import ExportOptions, write_document
    from opendoc_formats.fonts.resolver import FontResolver, _read_face
    from opendoc_formats.writers.docx_writer import write_docx_model

    usage = usage_at(tmp_path)
    source = usage.path.read_bytes()
    face = _read_face(usage.path)
    assert face is not None and face.subsettable
    resolver = FontResolver([face])
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: resolver))
    model = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun('AB', TextStyle(font_family=face.family))])])])
    before = document_to_json(model)
    target = tmp_path/'keep.docx'
    target.write_bytes(b'Own previous destination')
    stop, calls = Event(), []
    original = subset.Subsetter.subset

    def interrupted(self, font):
        original(self, font)
        calls.append(True)
        stop.set()

    monkeypatch.setattr(subset.Subsetter, 'subset', interrupted)
    if public:
        report = write_document(model, target, options=ExportOptions(cancelled=stop.is_set))
        assert not report.success and any(issue.feature == 'export.cancelled' for issue in report.issues)
    else:
        with pytest.raises(OperationCancelledError):
            write_docx_model(model, target, cancelled=stop.is_set)
    assert calls == [True]
    assert target.read_bytes() == b'Own previous destination'
    assert usage.path.read_bytes() == source and document_to_json(model) == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ['keep.docx', 'own.ttf']
