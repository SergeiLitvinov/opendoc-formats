"""A long native style chain can stop before reaching its next ancestor."""

from threading import Event

import pytest
from opendoc_model import Paragraph, document_to_json

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.ooxml.headings import import_heading
from opendoc_formats.support.cancellation import cancellation_scope, checkpoint


def test_cancel_inside_heading_style_inheritance(monkeypatch, tmp_path):
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.styles.style import ParagraphStyle
    from opendoc_model import DocumentModel, Section

    document = Document()
    base = document.styles.add_style('Own base', WD_STYLE_TYPE.PARAGRAPH)
    child = document.styles.add_style('Own child', WD_STYLE_TYPE.PARAGRAPH)
    child.base_style = base
    native = document.add_paragraph('Own paragraph', style=child)
    path = tmp_path / 'source.docx'
    document.save(path)
    source = path.read_bytes()
    paragraph = Paragraph()
    model = DocumentModel(sections=[Section(blocks=[paragraph])])
    original = document_to_json(model)
    stop, calls = Event(), []
    descriptor = ParagraphStyle.base_style

    def first(style):
        assert not calls, 'The next style ancestor was resolved after cancellation'
        result = descriptor.fget(style)
        calls.append(True)
        stop.set()
        return result

    with monkeypatch.context() as context:
        context.setattr(ParagraphStyle, 'base_style', property(first, descriptor.fset))
        with pytest.raises(OperationCancelledError):
            with cancellation_scope(stop.is_set, 'Own heading import'):
                import_heading(native, paragraph)
    assert calls == [True]
    assert document_to_json(model) == original
    assert path.read_bytes() == source
    checkpoint()
    import_heading(native, paragraph)
